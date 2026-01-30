# IPVO 2025/26 – Data-Intensive Web Application

This repository contains a data-intensive web application developed as part of the **IPVO course (2025/26)**.

The project demonstrates the design and implementation of a **scalable, reliable, and distributed system** for processing and analysing personal financial transactions, following the required IPVO project phases.

**Authors:**  
- Lovro Krapić  
- Marko Balenović  

---

## Project Overview

The application is a **personal finance tracking system** that allows users to:

- store and manage financial transactions,
- search and filter transactions efficiently,
- analyse spending behaviour over time,
- receive alerts when unusual spending patterns are detected.

The system is designed as a **distributed, containerized architecture**, focusing on scalability, reliability, and separation of concerns.

---

## System Architecture

The system consists of the following components:

- **REST API (FastAPI)**  
  Provides CRUD operations for users and transactions and serves as the main entry point.

- **MongoDB (NoSQL, replica set)**  
  Used as the primary persistent data store for transactions and alerts.  
  Replica set configuration ensures data reliability and availability.

- **Elasticsearch**  
  Provides full-text search capabilities over transaction descriptions, categories, and tags.

- **Redpanda (Kafka-compatible streaming platform)**  
  Used for asynchronous event streaming of newly created transactions.

- **Alert Processing Service**  
  A separate consumer service that processes transaction events and detects spending anomalies.

- **Redis**  
  Used for storing temporary metrics, historical spending baselines, and evaluating the usefulness of caching aggregated data.

- **Nginx**  
  Acts as a reverse proxy and entry point, enabling load balancing and future horizontal scaling.

All components are containerized using **Docker and Docker Compose**, allowing reproducible local deployment and cloud readiness.

---

## Project Phases

Although implemented as a single integrated system, the project fulfills all required IPVO phases.

---

### Phase 1 – Core Functionality and Reliable Storage (Implemented)

Phase 1 focuses on building the system foundation:

- REST API with CRUD endpoints for users and transactions
- Persistent storage using MongoDB
- Replica set configuration to improve data reliability
- Stateless API design enabling horizontal scaling
- Containerized deployment using Docker Compose

This phase ensures correctness, availability, and a scalable baseline architecture.

---

### Phase 2 – Full-Text Search (Implemented)

Phase 2 introduces efficient data access and querying:

- Elasticsearch used for full-text search over transactions
- Synchronization of transaction data from MongoDB to Elasticsearch
- Search API supporting text queries combined with filters (date, category, amount range)

This phase demonstrates how separating search workloads from the primary database improves performance and scalability.

---

### Phase 3 – Streaming, Alerts, and Aggregation (Implemented)

Phase 3 extends the system with asynchronous processing and analytics:

- Event streaming using Redpanda (Kafka API)
- Each new transaction is published as an event
- A dedicated alert-processing service consumes events asynchronously
- Historical spending metrics are maintained per user and category
- Alerts are generated when spending significantly deviates from historical behaviour
- Redis is used to evaluate the performance impact of caching aggregated monthly data

This phase demonstrates event-driven architecture, eventual consistency, and performance optimization strategies.

---

### Phase 4 – Future Work (AI/ML Integration)

Phase 4 is planned as future work and is **not implemented**, as specified by the course requirements.

The system is designed to support future AI/ML models that could:

- predict future spending based on historical aggregates,
- provide personalized budgeting recommendations,
- detect long-term behavioural trends.

The necessary historical and aggregated data required for such models is already available.

---

## Reliability and Scalability

The system ensures reliability and scalability through:

- Database replication (MongoDB replica set)
- Stateless API services with multiple instances
- Load balancing via Nginx
- Asynchronous event processing to prevent blocking critical paths
- Separation of concerns between services

Each component can be scaled independently based on system load.

---

## Key Challenges and Insights

Key challenges addressed during the project include:

- integrating multiple distributed systems into a stable architecture,
- initializing and managing database replication in a containerized environment,
- designing an alerting mechanism that avoids false positives,
- balancing consistency and performance using asynchronous processing.

The project provided hands-on experience with designing and reasoning about real-world data-intensive systems.

---

## Running the Project

The entire system can be started locally using Docker Compose:

```bash
docker compose up --build
