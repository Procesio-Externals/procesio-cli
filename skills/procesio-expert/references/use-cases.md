> Last verified: March 2026

# PROCESIO Use Cases — Canonical Reference

This is the **single source of truth** for all PROCESIO use cases.
No other file in this skill should contain use case descriptions — only pointers to this file.

Use cases are organized into **9 generic categories** covering **27 specific variants**.
Each entry includes: who needs it, what PROCESIO does, key benefits, industries, and PROCESIO features used.

---

## How to Use This File

- **Sales discovery**: match the prospect's pain to a category → use the description as a conversation guide
- **Use case evaluation**: start here before running the ELTP framework (see SKILL.md)
- **Industry lookup**: use the Industries column to find relevant use cases by sector
- **"Can PROCESIO do X?" questions**: scan categories and variants before saying no

**Industries key**: Retail | Production/Manufacturing | Utilities | Legal/Finance | HR | E-commerce | Oil & Gas | Cross-industry

---

## Category 1: Regulatory Compliance (eFactura & eTransport)

### 1.1 — eFactura (Romanian e-Invoicing)

**Who needs it:** Any company operating in Romania with an ERP system (SAP, Navision, Dynamics, custom group ERP) that must comply with mandatory e-invoicing via the national SPV/eFactura system.

**What PROCESIO does:**
- Sends issued invoices to the eFactura system automatically
- Receives and processes incoming invoices from eFactura (SPV)
- Provides a centralized dashboard: filter invoices, download associated files, extract reports, generate proof-of-submission for authorities
- Integrates using existing integration methods already in place at the client
- Implementation in **max 3 days**

**Key benefits:**
1. Short implementation time (weeks, not months)
2. Flexible implementation adapted to existing company processes and systems
3. Minimal involvement required from business and IT teams
4. Fully adapts to company-specific business processes
5. Extensible: approval flows, custom invoicing, multi-entity support, etc.

**Industries:** Retail, Production/Manufacturing, Utilities, Legal/Finance

**PROCESIO features:** Call API (SPV/eFactura API), Document Designer, Scheduling, Forms & Tasks (dashboard), SQL (invoice data)

**Related:** See also 1.2 (eTransport), sales-offer.md for eInvoice-specific pricing (volume model: €/100k invoices/year + 10%/year legal update maintenance)

---

### 1.2 — eTransport (Romanian Transport Declaration)

**Who needs it:** Production companies, transporters, retailers who must declare goods transport in the eTransport system (SPV) before movement begins.

**What PROCESIO does:**
- Collects information about transported goods from multiple source formats (files, APIs, ERP data)
- Declares transport in the eTransport platform (SPV) automatically
- Collects vehicle registration numbers for each transport
- Allows data updates and real-time GPS tracking via a **mobile app for drivers** (sends GPS position every 2 minutes)
- Centralized eTransport HUB covering all regulatory requirements in one platform

**Key benefits:**
1. Short implementation time (weeks)
2. Flexible implementation adapted to company processes and data typology (files, formats, structures)
3. Minimal business and IT involvement
4. Adaptable to any type of transport information format
5. Extensible: approval for certain conditions, transport pause/hold, etc.

**Industries:** Retail, Production/Manufacturing, Legal/Finance

**PROCESIO features:** Call API (SPV/eTransport API), Scheduling, Forms & Tasks (HUB dashboard), on-prem agent (internal ERP data), Mobile integration (GPS app)

---

## Category 2: Document Intelligence (Data Extraction)

*This is a family of related capabilities — PROCESIO reads documents from any source, extracts structured data using AI/OCR integrations, and routes or stores results. The variants differ in document type and source channel.*

### 2.1 — Order Management System (OMS) from Email

**Who needs it:** Companies managing high volumes of orders received by email, where each order comes with multiple messages and file attachments (common in FMCG, beverages, wholesale distribution).

**What PROCESIO does:**
- Continuously monitors designated email inboxes for incoming orders
- Automatically extracts data from attachments (Excel, PDF, CSV)
- Saves structured data to a centralized database
- Provides a visual dashboard with filters, pagination, and quick access to all orders and files
- Tracks order status end-to-end in a single interface

**Real case:** A beverage industry client received orders by email with multiple messages and attachments per order. Manual management was slow and error-prone. PROCESIO automated the entire ingestion, extraction, and tracking flow.

**Key benefits:**
1. Eliminates manual email and file management — significantly reduces errors and processing time
2. Complete order visibility via a centralized, filterable dashboard
3. Highly adaptable to any document type or order source
4. End-to-end traceability: every order and attachment recorded and trackable in real time

**Industries:** Retail, Production/Manufacturing

**PROCESIO features:** Read Mailbox, Get File Data (Excel/PDF/CSV), SQL, Forms & Tasks (dashboard), Scheduling

---

### 2.2 — CV / Resume Data Extraction & Scoring

**Who needs it:** Companies with high CV volume in their recruitment process (HR departments, recruitment agencies).

**What PROCESIO does:**
- Extracts standard structured data from CVs: name, email, LinkedIn, phone, last position, last job date, etc.
- Analyzes the Job Description, generates AI evaluation criteria, and scores each CV against the JD
- Enriches CV data with public information searched on Google (social media profiles, professional data)

**Key benefits:**
1. Reduces CV analysis time dramatically
2. Rapid identification of qualified candidates
3. Reduces risk of losing good candidates due to slow selection (they accept another offer in the meantime)
4. Increases recruitment accuracy → reduces cost of bad hires

**Industries:** Retail, Production/Manufacturing, Utilities, Legal/Finance, HR (cross-industry)

**PROCESIO features:** Read Mailbox / sFTP (CV ingestion), Call API (LLM for scoring, Google for enrichment), Scripting (data parsing), SQL / Forms (candidate dashboard)

---

### 2.3 — Document Data Extraction from Email (Invoices, Annexes, Reports)

**Who needs it:** Companies with business flows where documents arrive by email and data must be extracted and correlated with other internal information (invoices, contracts, stock data, etc.).

**What PROCESIO does (multiple variants):**
- Extracts data from invoice annexes received in eFactura (SPV) that are missing information
- Extracts data from daily/periodic reports containing quantities/stock levels → monitors and alerts when stock falls below configured thresholds
- Routes received documents to a registry: classifies, registers, and routes to the correct department/person
- Receives client orders and intermediate documents → centralizes and displays in a filterable dashboard grouped by client

**Key benefits:**
1. Reduces accidental risks from human errors in processing
2. Eliminates manual effort and associated costs
3. Increases speed of internal processes and reliability of services provided

**Industries:** Legal/Finance (primary), cross-industry

**PROCESIO features:** Read Mailbox, Call API (AI/OCR for extraction), Decisional (routing), SQL, Forms & Tasks (dashboard), Send Email (alerts)

---

### 2.4 — Contract Data Extraction

**Who needs it:** Legal departments, procurement teams, M&A advisors, any company managing large volumes of contracts.

**What PROCESIO does:**
- Extracts key terms, dates, parties, obligations, and conditions from contracts
- Structures extracted data into a searchable database
- Flags anomalies, missing clauses, or expiring terms
- Connects to due diligence workflows (see 2.5)

**Key benefits:**
1. Reduces accidental risks from unprocessed contract information
2. Eliminates manual effort and associated costs
3. Increases speed of legal review processes
4. Creates a searchable, auditable contract repository

**Industries:** Retail, Production/Manufacturing, Utilities, Legal/Finance

**PROCESIO features:** Call API (LLM for extraction), SQL, Forms & Tasks (contract repository dashboard), Scripting

---

### 2.5 — M&A Due Diligence Automation

**Who needs it:** M&A advisory firms, law firms performing due diligence in company acquisition/sale processes.

**What PROCESIO does:**
- Automates the high-volume, low-value part of due diligence: extracting data from large document sets
- Replaces expensive expert time spent on document reading and data entry
- Classifies and analyzes documents from multiple entities simultaneously
- Outputs structured data for expert review and reporting

**Key benefits:**
1. Increases due diligence capacity with the same team
2. Shortens the time to complete a due diligence process
3. Increases profitability of due diligence engagements (experts focus on analysis, not data extraction)

**Industries:** Legal/Finance

**PROCESIO features:** sFTP / Read Mailbox (document ingestion), Call API (LLM/OCR), SQL, Document Designer (output reports), Forms & Tasks (review interface)

---

## Category 3: Order & Email Monitoring

### 3.1 — Order Monitoring from Email

**Who needs it:**
- Manufacturing companies that sell wholesale and receive orders (and related documents) by email or multiple channels
- Companies with high order volume via email (e.g., international translation companies)

**What PROCESIO does:**
- Monitors email continuously, picks up orders, reads attachments, extracts data
- Stores everything in a database
- Provides a centralized dashboard: all orders, statuses, content, received files, and any adjustments over time

**Key benefits:**
1. Simplifies order processing and tracking
2. Eliminates human error risk in order capture and client delivery
3. Enables unlimited business scaling while maintaining the same client communication channel — without scaling costs

**Industries:** Cross-industry (especially wholesale, logistics, translation services)

**PROCESIO features:** Read Mailbox, Get File Data, SQL, Forms & Tasks (dashboard), Scheduling

*Note: overlaps with 2.1 (OMS) — key difference is 3.1 focuses on monitoring/visibility, 2.1 focuses on full extraction and processing pipeline*

---

## Category 4: Approval Flows & Finance Automation

### 4.1 — Invoice Approval Flow (AP)

**Who needs it:** Companies with international ERP systems (SAP, Navision, Dynamics) or custom group ERPs that need a structured approval process for received invoices.

**What PROCESIO does:**
- Routes received invoices through a configurable approval chain
- Notifies approvers, collects decisions, escalates when SLA missed
- Flags non-conforming invoices (potential fraud detection)
- Posts approved invoices to ERP

**Key benefits:**
1. Reduces accidental risks from unprocessed invoice information
2. Eliminates manual effort and associated costs
3. Reduces fraud risk by identifying non-conforming invoices

**Industries:** Legal/Finance

**PROCESIO features:** Forms & Tasks (approval UI, task assignment), Send Email (notifications), Call API (ERP integration), SQL, Decisional (routing logic), Error Port (SLA breach handling)

---

### 4.2 — Invoice Line Mapping to Cost Centers & Accounting Notes

**Who needs it:** Companies with international ERP systems that need to map received invoice line items to cost centers and generate accounting entries.

**What PROCESIO does:**
- Reads invoice data (from ERP or email extraction)
- Applies mapping rules to assign line items to cost centers
- Generates accounting notes / journal entries
- Posts to ERP automatically

**Key benefits:**
1. Reduces accounting team workload
2. Reduces accidental errors from manual processing

**Industries:** Legal/Finance

**PROCESIO features:** SQL, Call API (ERP), Scripting (mapping logic), Map Process Data, Document Designer (accounting notes)

---

### 4.3 — Purchase Request (PR) & Purchase Order (PO) Automation

**Who needs it:** Companies with international ERPs managing procurement workflows.

**What PROCESIO does:**
- Receives purchase requests → routes for approval → converts to purchase orders
- Integrates with ERP for PO creation and tracking
- Manages approvals, rejections, and modifications

**Key benefits:**
1. Reduces procurement team workload
2. Reduces accidental errors from manual processing

**Industries:** Legal/Finance

**PROCESIO features:** Forms & Tasks (PR submission, approval), Call API (ERP), SQL, Decisional, Send Email

---

### 4.4 — Payment Notification Automation & AR Efficiency

**Who needs it:** Companies that: have field sales agents issuing manual receipts, use SAP (or similar) with limitations in notification/reconciliation, rely on WhatsApp/email for collections, emit frequent manual receipts, lack standardized payment notification processes.

**What PROCESIO does:**
- Automates payment notifications to clients across official channels
- Generates electronic receipts
- Manages collection workflows: notification → reminder → escalation
- Integrates with central ERP system
- Tracks payment status in a centralized dashboard

**Key benefits:**
1. Significantly reduces human errors
2. Reduces processing time (from order to cash collection)
3. Increases client satisfaction (fast confirmations, faster delivery, transparency)
4. Improves cash flow

**Industries:** Cross-industry (especially retail, distribution, utilities)

**PROCESIO features:** Send Email, Call API (ERP/SAP), Forms & Tasks (dashboard), SQL, Scheduling, Document Designer (receipts)

---

### 4.5 — Annual Balance Confirmation (B2B)

**Who needs it:** Companies with a large B2B client base that must annually confirm outstanding balances with each client.

**What PROCESIO does:**
- Imports balance data (file or ERP integration)
- Generates an official notification document for each client
- Sends notifications with a confirmation link
- Clients access links to confirm, adjust, or dispute
- Sends a second notification to clients who haven't responded within X days
- Centralized dashboard with confirmation status for all clients
- Can be extended with auto-generated tasks for finance team members to act on disputes

**Key benefits:**
- Structures and streamlines the balance confirmation process
- Provides proof of notifications sent and confirmations received (audit-ready)
- Extensible with manual task assignment for the finance team

**Industries:** Cross-industry (especially utilities, finance, logistics)

**PROCESIO features:** Call API (ERP), Document Designer (notification letters), Send Email, Forms (confirmation links), SQL, Scheduling, Forms & Tasks (dashboard + task assignment)

---

## Category 5: AI Agents

*This category covers use cases where PROCESIO orchestrates AI-powered workflows — typically combining an LLM or vision API with structured business processes.*

### 5.1 — WhatsApp Sales Chatbot (Business Card / Badge to CRM)

**Who needs it:** Sales departments that frequently meet new contacts at events, conferences, or meetings and need to capture contact data fast.

**What PROCESIO does:**
- Sales person photographs a business card or event badge → sends photo to a WhatsApp channel
- Bot extracts data from the photo using AI (OCR/vision)
- Searches Google for the person, identifies LinkedIn profile, extracts professional data
- Summarizes using LLM
- Pushes structured contact data directly to the CRM, associated with the sender

**Key benefits:**
1. Simplifies contact data centralization and CRM sync
2. Enables sales reps to get real-time enriched information about the person they're talking to

**Industries:** Cross-industry (sales teams)

**PROCESIO features:** Call API (WhatsApp Business API, LLM, Google Search, LinkedIn scraping, CRM), Scripting, SQL

**Third-party integrations:** WhatsApp Business API, OpenAI / Azure AI (vision + LLM), CRM (HubSpot, Salesforce, etc.)

---

### 5.2 — Sales Researcher (Prospect Intelligence)

**Who needs it:** Business development and sales teams that need enriched intelligence about a prospect before or during a sales interaction.

**What PROCESIO does:**
- Given a prospect name/company: searches LinkedIn, Facebook, Google, and other public sources
- Enriches existing CRM data with current public information
- Generates a prospect profile summary using LLM

**Key benefits:**
- Gives sales reps comprehensive prospect intelligence without manual research
- Enables more personalized, informed outreach

**Industries:** Retail, Production/Manufacturing, Utilities, Legal/Finance, Cross-industry

**PROCESIO features:** Call API (Google, LinkedIn, LLM), Scripting (web enrichment), SQL / CRM integration

---

### 5.3 — Customer Email Automation (Classification & Routing)

**Who needs it:** Companies with high volumes of inbound customer emails requiring classification, routing, and/or automated resolution.

**What PROCESIO does:**
- Monitors inbound email
- Extracts data from messages and attachments
- Classifies messages (complaint, request, order, inquiry, etc.)
- Routes to the correct department or person
- For known request types: resolves automatically (sends response, triggers process)

**Key benefits:**
- Reduces manual email triage workload
- Ensures correct and fast routing
- Enables automatic resolution of high-volume, repetitive requests

**Industries:** Retail, Production/Manufacturing, Utilities, Legal/Finance

**PROCESIO features:** Read Mailbox, Call API (LLM for classification), Decisional (routing), Send Email (auto-response), Forms & Tasks (human routing dashboard)

---

### 5.4 — Rapid Credit Application (IFN via WhatsApp/Chat)

**Who needs it:** Non-bank financial institutions (IFN/NBFI) that want to automate the credit application intake process.

**What PROCESIO does:**
- Deploys an AI agent on WhatsApp (or other chat channel) to guide applicants through the credit intake process
- Follows a pre-configured flow to collect required information
- Integrates with the IFN's scoring systems
- Optionally integrates with KYC tools for identity verification

**Industries:** Legal/Finance (IFN/NBFI)

**PROCESIO features:** Call API (WhatsApp Business API, LLM, scoring engine, KYC tools), Decisional (flow control), SQL (application data), Forms & Tasks (agent dashboard)

---

### 5.5 — Customer Complaints & Support Automation

**Who needs it:** Companies with high volumes of customer complaints or support requests (utilities, retail, regulated industries).

**What PROCESIO does:**
- Intercepts inbound complaints/requests (email, form, API)
- Classifies and routes to the correct team
- Resolves automatically where policy allows
- Ensures regulatory compliance and response standards
- Tracks SLAs and escalates breaches

**Industries:** Utilities, Legal/Finance

**PROCESIO features:** Read Mailbox / Webhooks (ingestion), Call API (LLM classification), Forms & Tasks (agent workflow), Send Email (client responses), Decisional, Scheduling (SLA checks)

---

### 5.6 — Audio Transcription & Summarization

**Who needs it:** Any team that conducts meetings, calls, or interviews and needs structured records (sales, legal, HR, customer support).

**What PROCESIO does:**
- Receives audio file (meeting recording, call recording, interview)
- Sends to transcription API (e.g., Azure Speech, OpenAI Whisper)
- Processes transcript with LLM → generates summary, action items, key decisions
- Stores and routes output (email, CRM, database, document)

**Industries:** Retail, Production/Manufacturing, Utilities, Legal/Finance, Cross-industry

**PROCESIO features:** Call API (transcription API, LLM), Scripting, Document Designer (summary document), SQL / Send Email

**Third-party integrations:** Azure Speech Services, OpenAI Whisper, or similar

---

## Category 6: KYC & Identity Verification

### 6.1 — Client Onboarding Portal (Digital KYC)

**Who needs it:** Any company that acquires clients through its website and wants to make the onboarding process fully digital, fast, and error-free (utilities, financial services, insurance, regulated sectors).

**What PROCESIO does:**
- Client accesses onboarding portal on the company website
- Uploads documents (ID, invoices, property contracts) → AI extracts data automatically
- Client verifies and completes extracted information
- Client previews contractual documents to be signed
- Signs electronically or by hand, depending on process requirements
- Back-office process: fully automated, or with configured manual approval steps depending on internal policy

**Real case:** Energy sector client onboarding portal — reduces onboarding time by up to 90%.

**Key benefits:**
1. Reduces onboarding time by up to 90% through automated data collection and validation
2. Eliminates human errors via real-time AI extraction and validation
3. Increases conversion rate with a seamless, fully digital client experience
4. Instant scalability: adaptable for multiple service types, integrable with existing CRM/ERP

**Industries:** Utilities, Legal/Finance

**PROCESIO features:** Forms & Tasks (portal UI), Call API (AI/OCR for doc extraction, e-signature API), Document Designer (contracts), SQL, Webhooks

**Third-party integrations:** AI/OCR API, e-signature provider (e.g., DocuSign, RSign)

---

### 6.2 — License Plate Recognition (Oil & Gas / Fleet)

**Who needs it:** Companies that need to identify vehicle registration numbers of clients or commercial partners — e.g., to correlate fuel fills at pumps with company cards and associated vehicles.

**What PROCESIO does:**
- Camera or device captures vehicle image at point of entry/service
- PROCESIO sends image to a vision AI API for license plate recognition
- Extracted plate is matched against a database of registered cards/vehicles
- Authorizes or denies service; logs the transaction

**Industries:** Oil & Gas, Logistics

**PROCESIO features:** Call API (vision AI/OCR), SQL (vehicle/card database), Webhooks (device integration), Decisional (authorize/deny)

**Third-party integrations:** Azure Computer Vision, AWS Rekognition, or specialized ANPR API

---

### 6.3 — Prospect / Client / Partner Research & Scoring (KYC/AML)

**Who needs it:** Companies that need to profile prospects, clients, or partners from public or private sources — and score or alert based on risk (financial institutions, utilities, legal, logistics).

**What PROCESIO does:**
- Given a company CUI or person name: queries ANAF, PortalJust, Google, LinkedIn, Facebook, and other sources
- Correlates findings against company standards and risk criteria
- Generates a fit/risk score
- Triggers alerts if association with the person/company presents a risk

**Industries:** Retail, Production/Manufacturing, Utilities, Legal/Finance, Cross-industry

**PROCESIO features:** Call API (ANAF API, PortalJust scraping, Google, LinkedIn), Scripting (scoring logic), SQL, Send Email (alerts), Forms & Tasks (review dashboard)

**Third-party integrations:** ANAF API (Romania), PortalJust, Google Search API, LinkedIn

---

## Category 7: B2B Client Monitoring

### 7.1 — B2B Client Financial Monitoring via ANAF

**Who needs it:** Companies with a large B2B client base that need to monitor clients' financial health for risk indicators: credit scoring, financial risk assessment (utilities, lending companies, banks, NBFIs).

**What PROCESIO does:**
- Based on each company's CUI (Romanian tax ID), periodically extracts financial data from ANAF
- Calculates financial indicators from the data
- Generates alerts or recalculates credit scores based on changes
- Updates client risk profile in CRM/ERP

**Key benefits:**
- Reduces financial risks from clients in financial difficulty
- Enables proactive credit management instead of reactive

**Industries:** Legal/Finance (utilities, banks, NBFIs, credit companies)

**PROCESIO features:** Call API (ANAF API), Scripting (financial calculations), SQL, Scheduling (periodic extraction), Send Email (alerts), Call API (CRM/ERP for score update)

---

### 7.2 — Company Data Retrieval from ANAF

**Who needs it:** Any company that needs to retrieve official company data (financial, legal status, address, representatives) from ANAF using a CUI.

**What PROCESIO does:**
- Takes a CUI as input
- Calls ANAF API
- Returns and stores structured company data
- Can be used as a sub-process within larger KYC, onboarding, or risk workflows

**Industries:** Legal/Finance (broad applicability)

**PROCESIO features:** Call API (ANAF API), SQL, Map Process Data

*Note: This is typically used as a building block sub-process inside 6.3, 7.1, or any onboarding flow.*

---

## Category 8: Billing & ERP Integration

### 8.1 — Utility Re-Billing (Multi-Tenant)

**Who needs it:** Logistics parks, industrial parks, malls, office spaces, or commercial spaces that manage utility contracts and need to re-bill utilities to tenants based on complex, customizable rules.

**What PROCESIO does:**
- Manages multi-company setup with tenant contracts and utility consumption data
- Applies re-billing rules (by square meter, by meter reading, by consumption %, etc.)
- Generates invoices for each tenant automatically
- Eliminates manual complexity and error risk in multi-tenant utility billing

**Key benefits:**
- Manages complex re-billing rules that manual processes can't handle reliably
- Reduces error risk in multi-tenant financial workflows
- Scales to any number of tenants without additional operational cost

**Industries:** Legal/Finance, Utilities

**PROCESIO features:** SQL (contract and consumption data), Scripting (billing rule engine), Document Designer (invoices), Call API (ERP/accounting), Scheduling, Send Email

---

### 8.2 — VTEX E-Commerce Platform Integration

**Who needs it:** E-commerce companies using the VTEX platform (merchants, marketplaces) that need to connect VTEX with their internal ERP and business systems.

**What PROCESIO does:**
- Enables commercial partners to connect and exchange data: products, prices, stock, orders, delivery confirmations
- Handles the custom mapping required between VTEX's data model and each partner's internal systems and business flows
- Syncs in real time between platforms

**Key benefits:**
- Short implementation time
- Real-time synchronization between platforms
- Eliminates manual work
- Enables unlimited scaling
- Adapts to each partner's internal platforms and custom business flows

**Industries:** E-commerce, Retail

**PROCESIO features:** Webhooks (VTEX event triggers), Call API (VTEX API + ERP API), SQL, Scheduling, Map Process Data

---

## Category 9: Digital Signature & Certified Document Workflows

### 9.1 — Automated Digital Signature on Documents

**Who needs it:** Companies that produce, sell, or transport: controlled substances, valuables (jewellery), time-sensitive perishables, cold-chain products (meat, dairy, vaccines, pharmaceuticals), or items requiring traceability from order to delivery.

**What PROCESIO does:**
- Automates certified order confirmations and shipping updates
- Creates a dedicated tracking dashboard and collects signatures at each stage
- Integrates with existing systems: sends secure, tracked notifications (using **RMail** for certified email, **RSign** for e-signatures)
- Records delivery confirmations in CRM/ERP systems
- Generates audit-ready reports

**Key benefits:**
1. Compliance: legally valid signatures, court-admissible documentation
2. Error reduction: minimal manual errors in signing and tracking
3. Paperless: reduced printing and storage costs
4. Efficiency: sign and update from any location, instantly
5. Cost reduction: lower administrative and operational costs long-term

**Industries:** Cross-industry (pharma, food, logistics, legal, energy, luxury goods)

**PROCESIO features:** Call API (RMail API, RSign API, CRM/ERP), Document Designer (certificates, reports), Webhooks (delivery events), SQL, Forms & Tasks (tracking dashboard)

**Third-party integrations:** **RMail** (certified email), **RSign** (e-signature) — these are PROCESIO's current integration partners for this use case

---

## Third-Party Integrations Catalogue (from Use Cases)

The use cases above reveal specific third-party tools that PROCESIO integrates with in production. Reference this when clients ask about specific integrations:

| Third-party Tool | Used In | Type |
|-----------------|---------|------|
| **ANAF API** (Romanian Tax Authority) | 6.3, 7.1, 7.2 | REST API |
| **PortalJust** (Romanian court portal) | 6.3 | Web data |
| **WhatsApp Business API** | 5.1, 5.4 | REST API |
| **RMail** (certified email) | 9.1 | REST API |
| **RSign** (e-signatures) | 9.1 | REST API |
| **VTEX** (e-commerce) | 8.2 | REST API |
| **SAP / Navision / Dynamics** | 1.1, 4.1–4.3, 4.4 | REST API / sFTP / DB |
| **HubSpot / CRM** | 5.1, 5.2 | REST API |
| **OpenAI / Azure AI** | 2.2, 5.1–5.6 | REST API |
| **Azure Speech / Whisper** | 5.6 | REST API |
| **Google Search API** | 2.2, 5.2, 6.3 | REST API |
| **LinkedIn** | 2.2, 5.2, 6.3 | Scraping / API |
| **DocuSign / e-sign providers** | 6.1 | REST API |
| **Vision AI (ANPR)** | 6.2 | REST API |

---

## Industry → Use Case Quick Lookup

| Industry | Primary Use Cases |
|----------|-----------------|
| **Retail** | 1.1 eFactura, 1.2 eTransport, 2.1 OMS, 2.2 CV, 2.4 Contracts, 3.1 Order Monitoring, 5.2 Sales Researcher, 5.3 Email Automation, 5.6 Transcription, 6.3 KYC Research |
| **Production / Manufacturing** | 1.1 eFactura, 1.2 eTransport, 2.1 OMS, 2.2 CV, 2.4 Contracts, 3.1 Order Monitoring, 4.4 Payment Notifications, 5.2 Sales Researcher, 5.3 Email Automation, 5.6 Transcription, 6.3 KYC Research |
| **Utilities** | 1.1 eFactura, 4.5 Balance Confirmation, 5.3 Email Automation, 5.5 Complaints, 5.6 Transcription, 6.1 Onboarding Portal, 6.3 KYC Research, 7.1 Client Monitoring, 8.1 Re-Billing |
| **Legal / Finance** | 1.1 eFactura, 2.3 Doc Extraction, 2.4 Contracts, 2.5 M&A, 4.1 Invoice Approval, 4.2 Cost Centers, 4.3 PR/PO, 5.4 IFN Credit, 5.5 Complaints, 6.1 Onboarding, 6.3 KYC, 7.1 Client Monitoring, 7.2 ANAF, 8.1 Re-Billing |
| **HR / Recruitment** | 2.2 CV Extraction & Scoring |
| **E-commerce** | 8.2 VTEX Integration, 2.1 OMS |
| **Oil & Gas** | 6.2 License Plate Recognition |
| **Cross-industry** | 3.1 Order Monitoring, 4.4 Payments, 4.5 Balance Confirmation, 5.1 WhatsApp Chatbot, 5.2 Sales Researcher, 5.3 Email Automation, 5.6 Transcription, 6.3 KYC Research, 9.1 Digital Signature |

---

## Use Case → Integration Pattern Mapping

Each use case maps to one or more of the integration patterns in SKILL.md:

| Use Case | Primary Pattern |
|----------|----------------|
| eFactura / eTransport | Compliance Filing |
| OMS, Order Monitoring | Event-Driven Pipeline + Hub & Spoke |
| CV Extraction, Contract Extraction, Doc Extraction | AI Orchestration |
| M&A Due Diligence | AI Orchestration + File Exchange |
| Invoice Approval, PR/PO | Human-in-the-Loop (HITL) |
| KYC Onboarding Portal | HITL + Document Factory |
| WhatsApp AI Agent, Sales Researcher | AI Orchestration |
| Audio Transcription | Event-Driven Pipeline + AI Orchestration |
| Balance Confirmation | Document Factory + Polling Loop |
| Re-Billing, VTEX | Hub & Spoke |
| Digital Signature | Document Factory + HITL |
| ANAF Monitoring | Polling Loop |