import os
import json
import time
from datetime import datetime, timezone

from kafka import KafkaConsumer, KafkaProducer
from pymongo import MongoClient
import redis
from dateutil import parser as dtparser


KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TRANSACTIONS_TOPIC = os.getenv("TRANSACTIONS_TOPIC", "transactions")
ALERTS_TOPIC = os.getenv("ALERTS_TOPIC", "alerts")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
DB_NAME = os.getenv("DB_NAME", "finance")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

ALERT_STD_MULTIPLIER = float(os.getenv("ALERT_STD_MULTIPLIER", "2.5"))
MIN_BASELINE_COUNT = int(os.getenv("MIN_BASELINE_COUNT", "5"))
ABSOLUTE_ALERT_AMOUNT = float(os.getenv("ABSOLUTE_ALERT_AMOUNT", "1000"))  # demo-friendly absolute threshold

def now_utc():
    return datetime.now(timezone.utc)

def stats_key(user_id: str, category: str) -> str:
    return f"stats:{user_id}:{category}"

def load_stats(r: redis.Redis, key: str):
    h = r.hgetall(key)
    if not h:
        return 0, 0.0, 0.0
    return int(h.get(b"count", b"0")), float(h.get(b"mean", b"0")), float(h.get(b"m2", b"0"))

def save_stats(r: redis.Redis, key: str, count: int, mean: float, m2: float):
    r.hset(key, mapping={"count": str(count), "mean": str(mean), "m2": str(m2)})

def update_welford(count: int, mean: float, m2: float, x: float):
    count += 1
    delta = x - mean
    mean += delta / count
    delta2 = x - mean
    m2 += delta * delta2
    return count, mean, m2

def stddev(count: int, m2: float):
    if count < 2:
        return 0.0
    var = m2 / (count - 1)
    return var ** 0.5

def wait_for_kafka():
    while True:
        try:
            KafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP, api_version_auto_timeout_ms=5000).close()
            return
        except Exception as e:
            print(f"[alert] Kafka not ready: {e}")
            time.sleep(2)

def wait_for_mongo():
    while True:
        try:
            c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            c.admin.command("ping")
            return
        except Exception as e:
            print(f"[alert] Mongo not ready: {e}")
            time.sleep(2)

def main():
    print("[alert] starting alert consumer...")
    wait_for_kafka()
    wait_for_mongo()

    r = redis.Redis.from_url(REDIS_URL, decode_responses=False)

    mongo = MongoClient(MONGO_URI)
    db = mongo[DB_NAME]
    alerts_col = db["alerts"]

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        retries=3,
        linger_ms=10,
    )

    consumer = KafkaConsumer(
        TRANSACTIONS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="alert-service",
        enable_auto_commit=True,
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    print(f"[alert] consuming topic={TRANSACTIONS_TOPIC} bootstrap={KAFKA_BOOTSTRAP}")

    for msg in consumer:
        ev = msg.value
        if ev.get("eventType") != "transaction_created":
            continue

        user_id = ev["userId"]
        category = ev.get("category", "uncategorised")
        amount = float(ev.get("amount", 0))

        key = stats_key(user_id, category)
        count, mean, m2 = load_stats(r, key)

        s = stddev(count, m2)
        threshold = mean + ALERT_STD_MULTIPLIER * s if count >= MIN_BASELINE_COUNT else None

        is_anomaly = False
        reason = None
        # Primary rule: statistical anomaly once we have enough baseline
        if threshold is not None and s > 0:
            if amount > threshold:
                is_anomaly = True
                reason = f"amount {amount:.2f} > mean {mean:.2f} + {ALERT_STD_MULTIPLIER}*std {s:.2f}"
        # Fallback rule: if std is 0 but we have baseline, use mean multiple
        elif count >= MIN_BASELINE_COUNT and mean > 0:
            if amount > 1.8 * mean:
                is_anomaly = True
                reason = f"amount {amount:.2f} > 1.8*mean {mean:.2f}"
        # Demo-friendly rule: even without baseline, flag very large transactions
        elif amount >= ABSOLUTE_ALERT_AMOUNT:
            is_anomaly = True
            reason = f"amount {amount:.2f} >= absolute threshold {ABSOLUTE_ALERT_AMOUNT:.2f}"


        count2, mean2, m2_2 = update_welford(count, mean, m2, amount)
        save_stats(r, key, count2, mean2, m2_2)

        if not is_anomaly:
            continue

        occurred_at = ev.get("occurredAt")
        try:
            occurred_dt = dtparser.isoparse(occurred_at) if occurred_at else now_utc()
        except Exception:
            occurred_dt = now_utc()

        alert_doc = {
            "userId": user_id,
            "category": category,
            "transactionId": ev.get("id"),
            "amount": amount,
            "currency": ev.get("currency", "EUR"),
            "description": ev.get("description", ""),
            "reason": reason,
            "baseline": {"count": count, "mean": mean, "std": s, "threshold": threshold},
            "occurredAt": occurred_dt,
            "createdAt": now_utc(),
        }
        try:
            alerts_col.insert_one(alert_doc)
        except Exception as e:
            print(f"[alert] failed to persist alert: {e}")

        try:
            producer.send(ALERTS_TOPIC, {
                "eventType": "alert_created",
                "userId": user_id,
                "transactionId": ev.get("id"),
                "category": category,
                "amount": amount,
                "currency": ev.get("currency", "EUR"),
                "reason": reason,
                "createdAt": alert_doc["createdAt"].isoformat(),
            })
            producer.flush(timeout=1.0)
        except Exception as e:
            print(f"[alert] failed to publish alert: {e}")

        print(f"[alert] ALERT user={user_id} cat={category} amount={amount} reason={reason}")

if __name__ == "__main__":
    main()
