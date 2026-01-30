\
import os
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
from bson import ObjectId

import json
from kafka import KafkaProducer
import redis

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
DB_NAME = os.getenv("DB_NAME", "finance")

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TRANSACTIONS_TOPIC = os.getenv("TRANSACTIONS_TOPIC", "transactions")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ES_INDEX = os.getenv("ES_INDEX", "transactions")

es = Elasticsearch(ES_URL, request_timeout=10)

client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client[DB_NAME]
users_col = db["users"]
tx_col = db["transactions"]
alerts_col = db["alerts"]


# Optional Redis cache (Phase 3 evaluation)
_redis = None
def get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        _redis = redis.Redis.from_url(REDIS_URL)
    except Exception as e:
        print(f"[redis] not ready: {e}")
        _redis = None
    return _redis

def to_oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")

class UserCreate(BaseModel):
    email: str
    name: str

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    createdAt: datetime

class TransactionCreate(BaseModel):
    userId: str
    amount: int = Field(..., description="Amount in cents (e.g. 199 = €1.99)")
    currency: str = "EUR"
    category: str
    description: str = ""
    tags: List[str] = []
    occurredAt: datetime

class TransactionUpdate(BaseModel):
    amount: Optional[int] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    occurredAt: Optional[datetime] = None

class TransactionOut(BaseModel):
    id: str
    userId: str
    amount: int
    currency: str
    category: str
    description: str
    tags: List[str]
    occurredAt: datetime
    createdAt: datetime

app = FastAPI(title="Personal Finance Tracker - Phase 1 (Stable)")



def tx_doc_for_es(mongo_doc: dict, tx_id: str) -> dict:
    # Ensure JSON-serializable fields for Elasticsearch
    return {
        "id": tx_id,
        "userId": mongo_doc["userId"],
        "amount": int(mongo_doc["amount"]),
        "currency": mongo_doc.get("currency", "EUR"),
        "category": mongo_doc.get("category", ""),
        "description": mongo_doc.get("description", ""),
        "tags": mongo_doc.get("tags", []),
        "occurredAt": mongo_doc["occurredAt"].isoformat() if hasattr(mongo_doc.get("occurredAt"), "isoformat") else mongo_doc.get("occurredAt"),
        "createdAt": mongo_doc["createdAt"].isoformat() if hasattr(mongo_doc.get("createdAt"), "isoformat") else mongo_doc.get("createdAt"),
    }

async def ensure_indexes_forever():
    # Create indexes in background; never crash the app if Mongo isn't ready yet.
    while True:
        try:
            await db.command("ping")
            await users_col.create_index("email", unique=True)
            await tx_col.create_index([("userId", 1), ("occurredAt", -1)])
            await tx_col.create_index([("userId", 1), ("category", 1), ("occurredAt", -1)])
            print("[init] Indexes ensured.")
            return
        except Exception as e:
            print(f"[init] Mongo not ready yet: {e}")
            await asyncio.sleep(2)



async def ensure_es_index_forever():
    # Create ES index if missing; retry until ES is reachable.
    mapping = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "userId": {"type": "keyword"},
                "amount": {"type": "integer"},
                "currency": {"type": "keyword"},
                "category": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                "description": {"type": "text"},
                "tags": {"type": "keyword"},
                "occurredAt": {"type": "date"},
                "createdAt": {"type": "date"},
            }
        }
    }

    while True:
        try:
            if not es.indices.exists(index=ES_INDEX):
                es.indices.create(index=ES_INDEX, **mapping)
                print(f"[es] Created index: {ES_INDEX}")
            else:
                # Optionally update mapping? keep minimal.
                pass
            return
        except Exception as e:
            print(f"[es] Elasticsearch not ready yet: {e}")
            await asyncio.sleep(2)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(ensure_indexes_forever())
    asyncio.create_task(ensure_es_index_forever())

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate):
    doc = {
        "email": payload.email.strip().lower(),
        "name": payload.name.strip(),
        "createdAt": datetime.utcnow(),
    }
    try:
        res = await users_col.insert_one(doc)
    except Exception:
        raise HTTPException(status_code=409, detail="User with this email already exists")
    return UserOut(id=str(res.inserted_id), email=doc["email"], name=doc["name"], createdAt=doc["createdAt"])

@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str):
    doc = await users_col.find_one({"_id": to_oid(user_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(id=str(doc["_id"]), email=doc["email"], name=doc["name"], createdAt=doc["createdAt"])

@app.post("/transactions", response_model=TransactionOut)
async def create_transaction(payload: TransactionCreate):
    user = await users_col.find_one({"_id": to_oid(payload.userId)})
    if not user:
        raise HTTPException(status_code=400, detail="userId does not exist")
    doc = payload.model_dump()
    doc["createdAt"] = datetime.utcnow()
    res = await tx_col.insert_one(doc)
    tx_id = str(res.inserted_id)

    # Phase 3: publish to stream (best-effort)
    publish_transaction_event({
        "eventType": "transaction_created",
        "id": tx_id,
        "userId": doc["userId"],
        "amount": doc["amount"],
        "currency": doc.get("currency", "EUR"),
        "category": doc["category"],
        "description": doc.get("description", ""),
        "tags": doc.get("tags", []),
        "occurredAt": doc["occurredAt"].isoformat(),
        "createdAt": doc["createdAt"].isoformat(),
    })

    # Best-effort index in Elasticsearch (do not fail the request if ES is down).
    tx_id = str(res.inserted_id)
    try:
        es.index(index=ES_INDEX, id=tx_id, document=tx_doc_for_es(doc, tx_id))
    except Exception as e:
        print(f"[es] index failed for tx {tx_id}: {e}")

    return TransactionOut(id=tx_id, **doc)

@app.get("/transactions/{tx_id}", response_model=TransactionOut)
async def get_transaction(tx_id: str):
    doc = await tx_col.find_one({"_id": to_oid(tx_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionOut(
        id=str(doc["_id"]),
        userId=doc["userId"],
        amount=doc["amount"],
        currency=doc.get("currency", "EUR"),
        category=doc["category"],
        description=doc.get("description", ""),
        tags=doc.get("tags", []),
        occurredAt=doc["occurredAt"],
        createdAt=doc["createdAt"],
    )

@app.get("/transactions", response_model=List[TransactionOut])
async def list_transactions(
    userId: str = Query(...),
    fromDate: Optional[datetime] = Query(None),
    toDate: Optional[datetime] = Query(None),
    category: Optional[str] = Query(None),
    minAmount: Optional[int] = Query(None),
    maxAmount: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    q = {"userId": userId}
    if fromDate or toDate:
        q["occurredAt"] = {}
        if fromDate:
            q["occurredAt"]["$gte"] = fromDate
        if toDate:
            q["occurredAt"]["$lte"] = toDate
    if category:
        q["category"] = category
    if minAmount is not None or maxAmount is not None:
        q["amount"] = {}
        if minAmount is not None:
            q["amount"]["$gte"] = minAmount
        if maxAmount is not None:
            q["amount"]["$lte"] = maxAmount
    cursor = tx_col.find(q).sort("occurredAt", -1).limit(limit)
    out: List[TransactionOut] = []
    async for doc in cursor:
        out.append(TransactionOut(
            id=str(doc["_id"]),
            userId=doc["userId"],
            amount=doc["amount"],
            currency=doc.get("currency", "EUR"),
            category=doc["category"],
            description=doc.get("description", ""),
            tags=doc.get("tags", []),
            occurredAt=doc["occurredAt"],
            createdAt=doc["createdAt"],
        ))
    return out

@app.put("/transactions/{tx_id}", response_model=TransactionOut)
async def update_transaction(tx_id: str, payload: TransactionUpdate):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    res = await tx_col.update_one({"_id": to_oid(tx_id)}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    doc = await tx_col.find_one({"_id": to_oid(tx_id)})

    # Best-effort upsert to Elasticsearch
    try:
        es.index(index=ES_INDEX, id=tx_id, document=tx_doc_for_es(doc, tx_id))
    except Exception as e:
        print(f"[es] upsert failed for tx {tx_id}: {e}")

    return TransactionOut(
        id=str(doc["_id"]),
        userId=doc["userId"],
        amount=doc["amount"],
        currency=doc.get("currency", "EUR"),
        category=doc["category"],
        description=doc.get("description", ""),
        tags=doc.get("tags", []),
        occurredAt=doc["occurredAt"],
        createdAt=doc["createdAt"],
    )

@app.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str):
    res = await tx_col.delete_one({"_id": to_oid(tx_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Best-effort delete from Elasticsearch
    try:
        es.delete(index=ES_INDEX, id=tx_id)
    except NotFoundError:
        pass
    except Exception as e:
        print(f"[es] delete failed for tx {tx_id}: {e}")

    return {"deleted": True, "id": tx_id}


# -----------------------------
# Search (Phase 2 - Elasticsearch)
# -----------------------------
@app.get("/search/transactions")
async def search_transactions(
    userId: str = Query(...),
    q: str = Query("", description="Full-text query over description/category/tags"),
    fromDate: Optional[datetime] = Query(None),
    toDate: Optional[datetime] = Query(None),
    category: Optional[str] = Query(None),
    minAmount: Optional[int] = Query(None),
    maxAmount: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    must = [{"term": {"userId": userId}}]
    filters = []

    if q and q.strip():
        must.append({
            "multi_match": {
                "query": q,
                "fields": ["description", "category", "tags"]
            }
        })

    if fromDate or toDate:
        r = {}
        if fromDate:
            r["gte"] = fromDate.isoformat()
        if toDate:
            r["lte"] = toDate.isoformat()
        filters.append({"range": {"occurredAt": r}})

    if category:
        # exact match via keyword subfield if available
        filters.append({"term": {"category.raw": category}})

    if minAmount is not None or maxAmount is not None:
        r = {}
        if minAmount is not None:
            r["gte"] = minAmount
        if maxAmount is not None:
            r["lte"] = maxAmount
        filters.append({"range": {"amount": r}})

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filters
            }
        },
        "size": limit,
        "sort": [{"occurredAt": {"order": "desc"}}],
    }

    try:
        resp = es.search(index=ES_INDEX, body=body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Elasticsearch unavailable: {e}")

    hits = resp.get("hits", {}).get("hits", [])
    return {
        "count": len(hits),
        "results": [h.get("_source", {}) for h in hits],
    }


@app.post("/admin/reindex")
async def admin_reindex(userId: Optional[str] = Query(None), batchSize: int = Query(500, ge=50, le=2000)):
    # Rebuild ES index from Mongo (useful for initial sync or recovery).
    try:
        await db.command("ping")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Mongo unavailable: {e}")

    # Ensure ES index exists
    try:
        await ensure_es_index_forever()
    except Exception:
        pass

    q = {}
    if userId:
        q["userId"] = userId

    cursor = tx_col.find(q).sort("_id", 1)

    indexed = 0
    batch = []
    async for doc in cursor:
        tx_id = str(doc["_id"])
        batch.append(("index", tx_id, tx_doc_for_es(doc, tx_id)))
        if len(batch) >= batchSize:
            # Bulk API
            ops = []
            for action, _id, source in batch:
                ops.append({action: {"_index": ES_INDEX, "_id": _id}})
                ops.append(source)
            try:
                es.bulk(operations=ops, refresh=False)
                indexed += len(batch)
            except Exception as e:
                raise HTTPException(status_code=503, detail=f"Elasticsearch bulk failed: {e}")
            batch = []

    if batch:
        ops = []
        for action, _id, source in batch:
            ops.append({action: {"_index": ES_INDEX, "_id": _id}})
            ops.append(source)
        try:
            es.bulk(operations=ops, refresh=False)
            indexed += len(batch)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Elasticsearch bulk failed: {e}")

    return {"reindexed": indexed, "index": ES_INDEX, "userId": userId}


# -----------------------------
# Alerts (Phase 3)
# -----------------------------
@app.get("/alerts")
async def list_alerts(
    userId: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
):
    cursor = alerts_col.find({"userId": userId}).sort("createdAt", -1).limit(limit)
    out = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        doc.pop("_id", None)
        out.append(doc)
    return out


# Kafka producer (Phase 3 streaming)
_kafka_producer = None

def get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is not None:
        return _kafka_producer
    try:
        _kafka_producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            retries=3,
            linger_ms=10,
        )
    except Exception as e:
        print(f"[kafka] producer not ready: {e}")
        _kafka_producer = None
    return _kafka_producer

def publish_transaction_event(event: dict):
    # best-effort: do not fail request if Kafka is down
    prod = get_kafka_producer()
    if prod is None:
        return
    try:
        prod.send(TRANSACTIONS_TOPIC, event)
        prod.flush(timeout=1.0)
    except Exception as e:
        print(f"[kafka] send failed: {e}")


# -----------------------------
# Phase 3: Aggregates + optional cache evaluation
# -----------------------------
@app.get("/monthly_summary")
async def monthly_summary(
    userId: str = Query(...),
    year: int = Query(..., ge=1970, le=2100),
    month: int = Query(..., ge=1, le=12),
    useCache: bool = Query(True),
):
    key = f"monthly:{userId}:{year:04d}-{month:02d}"
    r = get_redis() if useCache else None

    if r is not None:
        try:
            cached = r.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"[redis] get failed: {e}")

    from_dt = datetime(year, month, 1, tzinfo=timezone.utc)
    to_dt = datetime(year + (1 if month == 12 else 0), (1 if month == 12 else month + 1), 1, tzinfo=timezone.utc)

    pipeline = [
        {"$match": {"userId": userId, "occurredAt": {"$gte": from_dt, "$lt": to_dt}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]

    results = []
    total_all = 0
    async for row in tx_col.aggregate(pipeline):
        results.append({"category": row["_id"], "total": row["total"], "count": row["count"]})
        total_all += row["total"]

    out = {
        "userId": userId,
        "year": year,
        "month": month,
        "total": total_all,
        "byCategory": results,
        "cache": bool(r is not None),
    }

    if r is not None:
        try:
            r.setex(key, 60, json.dumps(out))
        except Exception as e:
            print(f"[redis] set failed: {e}")

    return out
