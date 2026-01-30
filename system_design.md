
# System Design – Personal Finance Tracker

This document describes the architectural decisions and data flow of the Personal Finance Tracker application.

## Overview
The system is designed as a data-intensive, distributed web application focused on scalability, reliability, and fault tolerance.

## Architecture Components
- Nginx: Reverse proxy and load balancer
- FastAPI: Stateless REST API service
- MongoDB: Primary data store (replica set)
- Elasticsearch: Full-text search engine
- Redpanda: Event streaming platform
- Alert Service: Asynchronous event consumer
- Redis: Cache layer for frequent aggregations

## Data Flow
1. Client sends request through Nginx.
2. Request is routed to one of multiple FastAPI instances.
3. Transaction data is stored in MongoDB.
4. Transaction event is published to Redpanda.
5. Alert service consumes events and generates alerts.
6. Elasticsearch indexes transaction data.
7. Redis caches aggregated summaries.

## Fault Tolerance
- MongoDB replica set ensures data durability.
- Alert service failure does not block transactions.
- Elasticsearch failure affects search only.

## Scalability
- Horizontal scaling of API instances.
- Independent scaling of alert consumers.
- Streaming decouples processing load.

## Consistency Model
- Strong consistency for core transaction data.
- Eventual consistency for alerts and search.

## Future Improvements
- Authentication and authorization
- Monitoring and metrics
- Sharding and clustering
