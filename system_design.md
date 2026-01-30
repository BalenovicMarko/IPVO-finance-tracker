# System Design Document  
## IPVO 2025/26 – Data-Intensive Web Application

**Application name:** Personal Finance Tracking System  
**Authors:**  
- Lovro Krapić  
- Marko Balenović  

---

## 1. Application Idea and Scope

The application is a **personal finance tracking system** designed to store, process, and analyse large volumes of financial transaction data.  
Users can record transactions, search and filter historical data, analyse spending behaviour over time, and receive alerts when unusual spending patterns are detected.

The primary goal of the project is not feature completeness, but the **design and implementation of a scalable, reliable, and distributed data-intensive system**, following the principles discussed in the IPVO course.

The system is designed with **optimistic assumptions about user growth and data volume**, while carefully reasoning about trade-offs between consistency, availability, performance, and operational complexity.

---

## 2. Mapping to IPVO Project Phases

Although implemented as a single integrated system, the architecture fulfills all required IPVO project phases through the use of multiple complementary technologies and architectural patterns.

Each phase introduces new system components and data access patterns, increasing system complexity while preserving clarity and separation of concerns.

---

## 3. High-Level System Architecture

The system is built as a **distributed, containerized architecture**, composed of loosely coupled services communicating through synchronous APIs and asynchronous event streams.

### Core Components

- **REST API (FastAPI)**  
  Acts as the main entry point for clients.  
  Provides CRUD operations for users and financial transactions.  
  The API is stateless, enabling horizontal scaling.

- **MongoDB (NoSQL, replica set)**  
  Serves as the primary persistent data store for transactions and alerts.  
  A replica set configuration is used to ensure durability, availability, and fault tolerance.

- **Elasticsearch**  
  Provides full-text search and filtering capabilities over transaction data.  
  It is treated as a secondary, eventually consistent data store optimized for read-heavy workloads.

- **Redpanda (Kafka-compatible streaming platform)**  
  Enables asynchronous event streaming for newly created transactions.  
  Decouples transaction ingestion from downstream processing.

- **Alert Processing Service**  
  A dedicated consumer service that processes transaction events asynchronously.  
  Computes spending aggregates and detects anomalous behaviour.

- **Redis**  
  Used for temporary storage of aggregated metrics and historical spending baselines.  
  Evaluates the impact of caching on performance for frequently accessed data.

- **Nginx**  
  Acts as a reverse proxy and load balancer in front of API services.  
  Provides a single entry point and prepares the system for horizontal scaling.

All components are containerized using **Docker and Docker Compose**, ensuring reproducible deployments and cloud readiness.

---

## 4. Phase 1 – Core Functionality and Reliable Storage

### Objectives

Phase 1 establishes the system foundation by implementing a minimal but reliable architecture for storing and retrieving financial transactions.

### Implemented Components

- Stateless REST API service
- MongoDB replica set as the primary data store
- Nginx reverse proxy
- Docker-based local deployment

### Design Decisions

MongoDB was chosen as the primary database due to its flexible document-based data model, which fits transaction data with varying attributes.  
A **replica set** configuration is used to ensure durability and availability in the presence of node failures.

The REST API is designed to be **stateless**, allowing multiple instances to run in parallel behind a load balancer.  
Nginx provides request routing and enables future horizontal scaling.

### Reliability and Consistency

- Writes are acknowledged by the MongoDB primary node, ensuring durability.
- Replica set members provide redundancy and fast recovery.
- Strong consistency is preserved for core transactional data.

---

## 5. Phase 2 – Extended Functionality: Full-Text Search

### Objectives

Phase 2 introduces efficient querying and search capabilities, separating read-intensive workloads from the primary database.

### Implemented Components

- Elasticsearch cluster
- Data synchronization from MongoDB to Elasticsearch
- Search API endpoints with filtering support

### Design Decisions

Elasticsearch is used to handle full-text search over transaction descriptions, categories, and tags.  
This avoids expensive text queries on the primary database and improves system scalability.

Elasticsearch is treated as a **secondary, eventually consistent data store**.  
Temporary inconsistencies between MongoDB and Elasticsearch are acceptable, as search results do not require strict real-time accuracy.

---

## 6. Phase 3 – Advanced Functionality: Streaming, Alerts, and Aggregation

### Objectives

Phase 3 focuses on asynchronous processing, analytics, and performance optimization.

### Implemented Components

- Redpanda message broker
- Alert processing consumer service
- Redis caching layer

### Data Flow

1. A transaction is stored in MongoDB via the REST API.
2. A transaction event is published to Redpanda.
3. The alert processing service consumes events asynchronously.
4. Aggregated metrics are computed per user and category.
5. Alerts are generated and stored when anomalies are detected.

### Consistency and Trade-offs

Alert generation is **eventually consistent** with transaction creation.  
Temporary delays in alert visibility are acceptable, as they improve system responsiveness and decouple critical write paths from heavy computations.

Redis is used to cache aggregated data and evaluate performance improvements.  
If Redis fails, the system gracefully falls back to database queries.

---

## 7. Phase 4 – Future Work: AI/ML Integration (APVO)

Phase 4 is planned as future work and is not implemented as part of this project.

The system is intentionally designed to support future AI/ML components that could:
- predict future spending trends,
- generate personalized budget recommendations,
- detect long-term behavioural patterns.

The system already stores sufficient historical and aggregated data to support supervised or unsupervised learning models without major architectural changes.

---

## 8. Reliability, Fault Tolerance, and Recovery

The system addresses reliability and fault tolerance through:

- MongoDB replication for data durability
- Stateless services allowing fast restarts
- Asynchronous processing to isolate failures
- Graceful degradation in case of cache or search index failures

Single-node failures do not cause system-wide outages, and data loss is minimized through replication.

---

## 9. Scalability Considerations

The architecture supports scalability through:

- Horizontal scaling of API services
- Load balancing via Nginx
- Separation of write, search, and analytics workloads
- Event-driven processing for non-critical tasks

Each component can be scaled independently based on observed load patterns.

---

## 10. Key Challenges and Insights

Key challenges addressed during the project include:
- integrating multiple distributed systems into a coherent architecture,
- managing replication and consistency in a containerized environment,
- designing alert logic that balances sensitivity and false positives,
- reasoning about consistency trade-offs in asynchronous workflows.

The project provided practical experience in designing and reasoning about real-world data-intensive distributed systems.

---

## 11. Summary

This system demonstrates a complete data-intensive architecture implementing replication, asynchronous processing, caching, and horizontal scaling.  
All required IPVO project phases are implemented and integrated into a single, coherent system design that balances reliability, scalability, and maintainability.
