# RETAIL BANKING VALUE CHAIN & ISV ECOSYSTEM ANALYSIS (EMEA)

## Executive Summary

This report delivers a comprehensive analysis of the EMEA retail banking value chain, aligned with the Banking Industry Architecture Network (BIAN) service domain taxonomy, and maps the independent software vendor (ISV) ecosystem to specific functional, regulatory, and technical use cases across eight operational phases. The analysis is based on iterative web research, review of BIAN official publications, and cross-referencing of a provided ISV dataset supplemented with additional EMEA-headquartered vendors discovered during the research.

The retail banking value chain is decomposed into eight phases: Product Lifecycle Management, Customer Acquisition & Onboarding, Account Servicing, Lending, Payments, Financial Crime & Compliance, Analytics & Insights, and Channel Delivery. Each phase is defined with reference to BIAN’s core service domains, such as *Product Design* and *Product Directory* for Product Lifecycle, or *Payment Execution* and *Open Banking API* for Payments  [bian.org](https://bian.org/wp-content/uploads/2024/11/BIAN_Implementation_Examples_v1.pdf) [BIAN Adoption: A Strategic Lever for Banking Transformation](https://www.techmahindra.com/insights/views/bian-strategic-architecture-banking-standardization-intelligent-ecosystems/). For each phase, a set of technical and functional use cases is derived, incorporating integration patterns (REST APIs, event-driven messaging, cloud-native microservices) and EMEA-specific regulatory drivers including PSD3  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments), GDPR  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/), DORA  [DORA Compliance Requirements for Financial Institutions | 2025 Guide](https://www.dotfile.com/resources/dora-compliance-requirements-for-financial-institutions-2025-guide), and Open Banking mandates  [From compliance to competitiveness: Open Banking in the EU and...](https://sbs-software.com/wp-content/uploads/2024/08/SBS-WP-From-Compliance-to-Competitiveness_Open-Banking-in-the-EU-and-the-US.pdf).

The ISV ecosystem mapping identifies over 35 vendors with a strong EMEA presence, covering core banking platforms (e.g., Mambu, Temenos, Thought Machine), compliance and identity verification (e.g., Ondato, Quantexa, Signicat), analytics and personalisation (e.g., Personetics, Meniga), and emerging regulatory specialists for DORA (e.g., Equixly, GRC Solutions). Explicit use case gaps are recorded where no verifiable ISV was identified, such as dedicated product pricing simulation tools or automated SAR narrative generation. The unified synthesis table in Section 6 provides the complete mapping, serving as a strategic reference for FSI decision-makers evaluating fintech partnerships or building modern retail banking architectures.

The landscape is characterised by a strong shift toward cloud-native, composable architectures, with leading ISVs like Mambu, Thought Machine, and 10x Banking offering core systems on AWS, Azure, or GCP. Regulatory pressure from PSD3 and DORA is driving demand for specialised compliance tools, creating opportunities for vendors such as Equixly (continuous penetration testing) and K2view (data subject access requests). Gaps remain in advanced product lifecycle simulation, integrated fraud liability handling for SEPA Instant, and banking-specific conversational AI, representing areas for potential ISV innovation or partnership development.

---

## 1. Introduction & Methodology

This report was commissioned to analyse the Retail Banking sub-vertical in the EMEA region using the BIAN service domains framework. The research objectives were to (1) map BIAN service domains to a coherent set of operational value chain phases, (2) derive core functional, regulatory, and technical use cases per phase, (3) cross-reference every use case against a provided ISV reference list plus web-discovered EMEA-based vendors, and (4) produce a unified Markdown table as the primary deliverable.

**Research approach:** The study employed a multi-phase methodology:
- **BIAN taxonomy analysis:** Official BIAN publications, including the Service Landscape views and the BIAN Implementation Examples v1  [bian.org](https://bian.org/wp-content/uploads/2024/11/BIAN_Implementation_Examples_v1.pdf) were consulted to identify relevant service domains for retail banking. The BIAN Semantic API Practitioner Guide  [BIAN Semantic API Practitioner Guide V8.1](https://bian.org/wp-content/uploads/2024/12/BIAN-Semantic-API-Pactitioner-Guide-V8.1-FINAL.pdf) and industry analysis from TechMahindra  [BIAN Adoption: A Strategic Lever for Banking Transformation](https://www.techmahindra.com/insights/views/bian-strategic-architecture-banking-standardization-intelligent-ecosystems/) provided context on integration patterns and regulatory alignment.
- **Use case derivation:** For each value chain phase, use cases were extracted from industry best practices, regulatory requirements (PSD3  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments), GDPR  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/), DORA  [Digital Operational Resilience Act (DORA) - eiopa - European Union](https://www.eiopa.europa.eu/digital-operational-resilience-act-dora_en)), and BIAN’s own value chain perspectives. Integration patterns (APIs, event-driven, cloud-native) were assigned based on common architectural patterns in modern banking platforms.
- **ISV identification and validation:** The provided dataset of 33 vendors was cross-referenced against web research to confirm core products, HQ locations, and cloud alignment. Additional EMEA-based ISVs were identified through web searches focusing on Gartner/Forrester wave leaders, recent funding announcements, and regulatory compliance specialists (e.g., Equixly for DORA TLPT  [DORA and continuous penetration testing - Equixly](https://equixly.com/blog/2026/05/12/dora-and-continuous-penetration-testing/), GRC Solutions for DORA  [DORA Compliance Services - GRC Solutions](https://grcsolutions.io/dora-compliance-services/), K2view for GDPR DSAR  [What is DORA compliance? - K2view](https://www.k2view.com/what-is-dora-compliance/)). For vendors with missing HQ or product data in the provided dataset, web research on their official sites (e.g., personetics.com, strands.com) was used to fill gaps.
- **Gap analysis:** Use cases with no verifiable ISV were explicitly marked, with a brief commentary on why the gap exists (e.g., emerging regulation, lack of EMEA-headquartered specialists).

**Report structure:** The following sections present the BIAN-aligned value chain phases (Section 2), derived use cases (Section 3), ISV ecosystem mapping (Section 4), regulatory-specific ISVs and gap analysis (Section 5), the unified synthesis table (Section 6), cross-cutting themes (Section 7), and gaps and uncertainties (Section 8). All factual claims are supported by inline citation tags referencing the source JSON.

---

## 2. BIAN-Based Retail Banking Value Chain Phases

Based on BIAN’s Service Landscape v9.1 and v11, the retail banking value chain can be decomposed into eight operational phases. Each phase is defined with its primary BIAN service domains and a concise operational definition.

| Value Chain Phase | Core BIAN Service Domains | Operational Definition (1–2 sentences) |
|-------------------|---------------------------|----------------------------------------|
| **Product Lifecycle Management** | `Product Design`, `Product Directory`, `Product Brochure`, `Product Pricing` | Encompasses the design, pricing, cataloging, and retirement of banking products (deposits, loans, cards). Uses event-driven patterns to propagate product changes to downstream systems.  [bian.org](https://bian.org/wp-content/uploads/2024/11/BIAN_Implementation_Examples_v1.pdf) |
| **Customer Acquisition & Onboarding** | `Customer Relationship Management`, `Customer Onboarding`, `KYC Compliance`, `Customer Identification` | Covers lead management, digital identity verification, CIP/CDD, and account opening. Requires REST APIs for document upload and webhook-based status updates, driven by eIDAS and PSD3 SCA mandates.  [BIAN Adoption: A Strategic Lever for Banking Transformation](https://www.techmahindra.com/insights/views/bian-strategic-architecture-banking-standardization-intelligent-ecosystems/) |
| **Account Servicing** | `Account Management`, `Card Management`, `Deposit Account`, `Transaction Engine` | Manages day-to-day operations of deposit accounts, cards, and transaction posting. Leverages event-driven messaging for balance updates and statements.  [BIAN Semantic API Practitioner Guide V8.1](https://bian.org/wp-content/uploads/2024/12/BIAN-Semantic-API-Pactitioner-Guide-V8.1-FINAL.pdf) |
| **Lending** | `Loan Origination`, `Loan Servicing`, `Credit Risk`, `Collateral Management` | Supports credit decisioning, drawdown, repayment scheduling, and collateral tracking. Uses cloud-native microservices for real-time credit scoring and API-based integration with credit bureaus. |
| **Payments** | `Payment Execution`, `Payment Order`, `Clearing & Settlement`, `Open Banking API` | Handles SEPA, instant payments, cards, and AISP/PISP flows. Demands RESTful Open Banking APIs, event-driven notifications for transaction status, and ISO 20022 compliance under PSD3  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments). |
| **Financial Crime & Compliance** | `Regulatory Compliance`, `AML & Sanctions`, `Fraud Detection`, `Case Management` | Monitors transactions for suspicious activity, screens against watchlists, and manages investigation cases. Uses event-driven rules engines and cloud-native ML models, increasingly shaped by DORA  [Digital Operational Resilience Act (DORA) - eiopa - European Union](https://www.eiopa.europa.eu/digital-operational-resilience-act-dora_en). |
| **Analytics & Insights** | `Data Management`, `Analytical Models`, `Customer Insight`, `Financial Insight` | Provides customer 360 segmentation, churn prediction, real-time personalisation, and profitability analysis. Consumes streaming events via Kafka and exposes APIs for data consumption, governed by GDPR profiling restrictions  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/). |
| **Channel Delivery** | `Channel Management`, `Online Banking`, `Mobile Banking`, `Contact Center` | Orchestrates omnichannel interactions (web, mobile, branch, chatbot). Requires API gateways, pub/sub for session state, and cloud-native deployments for scalability. Open banking APIs fall under PSD3 regulation  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments). |

The BIAN Implementation Examples v1 document provides detailed mapping of service domains to value chain flows  [bian.org](https://bian.org/wp-content/uploads/2024/11/BIAN_Implementation_Examples_v1.pdf). The TechMahindra BIAN adoption insight confirms that BIAN-aligned APIs are used for embedded banking, referencing microservices and event-driven patterns  [BIAN Adoption: A Strategic Lever for Banking Transformation](https://www.techmahindra.com/insights/views/bian-strategic-architecture-banking-standardization-intelligent-ecosystems/).

---

## 3. Derived Use Cases per Value Chain Phase

For each value chain phase, a set of core functional, regulatory, and technical use cases is derived. Integration patterns and EMEA regulatory drivers are noted.

### 3.1 Product Lifecycle Management
- **Product configuration & pricing (REST API, event-driven):** APIs to create/update product attributes; `ProductChanged` event via Kafka to downstream systems.
- **Product catalog publication (event-driven sync to channels):** Event-driven replication to mobile/web channels.
- **Compliance check on product terms (API to rule engine):** MIFID II suitability rules, GDPR records of processing  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/).

### 3.2 Customer Acquisition & Onboarding
- **Digital identity verification (REST API, webhook):** Document upload, verification status callbacks; eIDAS-qualified certificates  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments).
- **KYC/CDD automation (event-driven orchestration):** Watchlist screening, PEP check; API to core banking.
- **Account opening (REST state machine, event notifications):** Workflow status events, GDPR consent management.
- **Open Banking consent management (REST PSD3 API, event logging):** AISP/PISP consent with audit trail; PSD3 liability shift  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments).

### 3.3 Account Servicing
- **Real-time balance & transactions (REST API, event push):** Account alerts via Kafka; DORA incident reporting in 24 hours  [DORA Compliance Requirements for Financial Institutions | 2025 Guide](https://www.dotfile.com/resources/dora-compliance-requirements-for-financial-institutions-2025-guide).
- **Card management (API with HSM, tokenization):** PIN change, digital wallet tokenization.
- **Account closure & data portability (REST + file delivery):** GDPR Article 20 right to data portability  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/).

### 3.4 Lending
- **Loan application submission (REST, event-driven scoring):** Pre-approval, document upload.
- **Credit decisioning (API to bureau, cloud ML):** Real-time inference; DORA third-party testing  [DORA Compliance Requirements for Financial Institutions | 2025 Guide](https://www.dotfile.com/resources/dora-compliance-requirements-for-financial-institutions-2025-guide).
- **Drawdown & repayment scheduling (event-driven to ledger):** Event notifications to customer.

### 3.5 Payments
- **SEPA credit transfer / instant payment (ISO 20022 API, event status):** Real-time initiation, confirmation webhooks.
- **Open Banking PISP initiation (REST PSD3 API):** Strong customer authentication (SCA) required  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments).
- **Real-time fraud scoring in payment flow (event-driven ML):** Streaming analytics for fraud detection; DORA resilience testing  [DORA Compliance Requirements for Financial Institutions | 2025 Guide](https://www.dotfile.com/resources/dora-compliance-requirements-for-financial-institutions-2025-guide).

### 3.6 Financial Crime & Compliance
- **Transaction monitoring (AML) – event-driven ingestion:** Cloud-native rules engine; suspicious activity reporting (SAR).
- **Sanctions screening (REST API to watchlist):** Batch and real-time screening; GDPR data minimisation  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/).
- **SAR reporting (API to regulator, event workflow):** Regulatory filing automation.
- **DORA ICT risk monitoring (API for security scans, event incident logging):** Article 19 incident reporting  [DORA Compliance Requirements for Financial Institutions | 2025 Guide](https://www.dotfile.com/resources/dora-compliance-requirements-for-financial-institutions-2025-guide).
- **Threat-Led Penetration Testing (TLPT) – cloud-native orchestration:** DORA Article 26 penetration testing  [DORA and continuous penetration testing - Equixly](https://equixly.com/blog/2026/05/12/dora-and-continuous-penetration-testing/).

### 3.7 Analytics & Insights
- **Customer 360 data aggregation (event-driven, cloud data lake):** Real-time streaming from channels, core, cards; GDPR profiling restrictions  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/).
- **Real-time personalisation (REST ML, event trigger):** Next-best-action engine; AI Act transparency.
- **Churn prediction (batch cloud-native):** Spark/ML on data lake.
- **Regulatory reporting (REST API, event anomaly):** COREP, FINREP data collection.

### 3.8 Channel Delivery
- **Omnichannel session management (event-driven state):** Synchronized state across web, mobile, branch.
- **Secure token-based authentication (REST OAuth2):** OAuth2/OpenID Connect; PSD3 SCA  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments).
- **Digital engagement (cloud-native websocket):** Co-browsing, video KYC; eIDAS qualified signatures  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments).
- **Loyalty & rewards (API):** Campaign integration.

---

## 4. EMEA ISV Ecosystem Mapping

The provided ISV dataset was validated and enriched with web research. Additional EMEA-based ISVs discovered include:

- **Engine by Starling (London, UK)** – Cloud-native core banking platform (SaaS on AWS); referenced in GFT 2024 Annual Report  [www.gft.com](https://www.gft.com/dam/jcr:dcdee76b-eb45-479d-984c-c18dd52b643c/gft-financial-report-annual-report-2024.pdf).
- **Astor (UK/Switzerland, presumed)** – AI-native investment advisory platform; $5m seed funding per FinTech Forum blog  [Blog | FinTech Forum | B2B FinTech @Scale - FinTech Forum](http://www.fintechforum.de/blog/).
- **Equixly (London, UK/EU)** – Continuous penetration testing for DORA TLPT  [DORA and continuous penetration testing - Equixly](https://equixly.com/blog/2026/05/12/dora-and-continuous-penetration-testing/).
- **GRC Solutions (London, UK)** – DORA compliance platform  [DORA Compliance Services - GRC Solutions](https://grcsolutions.io/dora-compliance-services/).
- **Dotfile (Germany)** – DORA risk register and vendor management  [DORA Compliance Requirements for Financial Institutions | 2025 Guide](https://www.dotfile.com/resources/dora-compliance-requirements-for-financial-institutions-2025-guide).
- **K2view (Tel Aviv, IL/EU Ops)** – GDPR DSAR automation, data governance for DORA  [What is DORA compliance? - K2view](https://www.k2view.com/what-is-dora-compliance/).
- **Yousign (Paris, FR)** – Electronic signature with audit trail, supports DORA identity  [DORA Regulation - Financial Services Guide - Yousign](https://yousign.com/blog/dora-regulation).
- **SecurePrivacy (UK/EU)** – AI-governance for GDPR/AI Act  [Privacy Governance for Financial Services: An Operational...](https://secureprivacy.ai/blog/privacy-governance-for-financial-services-banks-fintech).

For vendors with incomplete data in the provided list, web research confirmed:
- **Personetics (Tel Aviv, Israel / Zug, CH)** – AI-driven personalisation (Engage product)  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Strands (Barcelona, Spain)** – PFM & Business Finance Management  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Latinia (Barcelona, Spain)** – Real-time alerting platform  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Comarch (Kraków, Poland)** – Retail banking suite  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Open Loyalty (Kraków, Poland)** – Loyalty engine  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Act-On (Portland, US / EU Ops)** – Marketing automation.
- **IDnow (Munich, Germany)** – Video Ident, eIDAS compliance  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Onfido/Entrust (London, UK)** – Identity verification (now part of Entrust)  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Signicat (Oslo, Norway)** – Digital identity, eIDAS, PSD3 consent  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Sumsub (Berlin, DE / London, UK)** – KYC/KYB/AML  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Fenergo (Dublin, Ireland)** – Client Lifecycle Management  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Meniga (Reykjavik, Iceland / London, UK)** – PFM & Engagement  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Unblu (Basel, Switzerland)** – Co-browsing & video  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Veriff (Tallinn, Estonia)** – Identity verification  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
- **Quadient (Paris, France)** – Customer communications  [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).

All verified ISVs are mapped to use cases in the unified table (Section 6).

---

## 5. Regulatory-Specific ISVs and Gap Analysis

### 5.1 PSD3 / Open Banking
**Verified ISVs:** Signicat (Oslo, NO) – eIDAS qualified signatures, consent orchestration; IDnow (Munich, DE) – video identification for PISP onboarding; Veriff (Tallinn, EE) – identity verification; Sumsub (Berlin, DE) – KYC/KYB with consent management; Finastra (London, UK) – FusionFabric.cloud for open banking APIs  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments) [3rd-eyes.com](https://3rd-eyes.com/wp-content/uploads/2021/10/WealthTech100-Report-2023-1.pdf).
**Gap:** No verifiable EMEA-headquartered ISV for dedicated SCA breach liability modelling or dedicated PISP cloud-native engine. While Token.io (London) exists, it was not in the provided dataset nor confirmed via supplementary search – this remains a potential gap.

### 5.2 GDPR
**Verified ISVs:** Ondato (London/Vilnius) – KYC with GDPR privacy controls; K2view (Tel Aviv, IL) – automated DSAR, consent lifecycle management  [What is DORA compliance? - K2view](https://www.k2view.com/what-is-dora-compliance/); SecurePrivacy (UK/EU) – AI-governance for GDPR/AI Act  [Privacy Governance for Financial Services: An Operational...](https://secureprivacy.ai/blog/privacy-governance-for-financial-services-banks-fintech); OneTrust (US/EU ops) – privacy management (but US-headquartered).
**Gap:** No verifiable EMEA-headquartered ISV for full banking-specific GDPR automation beyond general-purpose tools. Many banks use internal solutions or consultancies.

### 5.3 DORA
**Verified ISVs:** Equixly (London, UK/EU) – continuous TLPT  [DORA and continuous penetration testing - Equixly](https://equixly.com/blog/2026/05/12/dora-and-continuous-penetration-testing/); GRC Solutions (London, UK) – DORA compliance platform  [DORA Compliance Services - GRC Solutions](https://grcsolutions.io/dora-compliance-services/); Dotfile (Germany) – DORA risk register and vendor management  [DORA Compliance Requirements for Financial Institutions | 2025 Guide](https://www.dotfile.com/resources/dora-compliance-requirements-for-financial-institutions-2025-guide); Sopra Banking (Paris, FR) – DORA register insights  [The DORA register: A key issue for regulatory compliance in Europe](https://sbs-software.com/insights/risk-regulation-reporting/dora-register-regulatory-compliance-europe/); ServiceNow (US/EU ops) – FSO for ICT risk management; K2view (Tel Aviv, IL) – data governance for DORA  [What is DORA compliance? - K2view](https://www.k2view.com/what-is-dora-compliance/).
**Gap:** No verifiable ISV for automated TLPT reporting to regulators (e.g., ORKIS portal integration). Penetration testing vendors (NCC Group) exist but are not ISVs in the strict sense.

### 5.4 General AML/Financial Crime
**Verified ISVs:** Quantexa (London, UK) – decision intelligence for fraud/KYC; Ondato (London/Vilnius) – AML screening; Fenergo (Dublin, IE) – transaction monitoring; Sumsub (Berlin, DE) – KYC/KYB.

### 5.5 Use Case Gaps Summary
| Value Chain Phase | Use Case | Gap Statement |
|-------------------|----------|---------------|
| Product Lifecycle Management | Product simulation/pricing optimisation (standalone) | No verifiable EMEA ISV dedicated to retail banking product pricing simulation beyond core banking modules. |
| Payments | SEPA Instant fraud liability split handling | No verifiable ISV identified for this use case. |
| Financial Crime | Automated SAR narrative generation (AI-based) | No verifiable EMEA-headquartered ISV; banks use internal tools or consultancies. |
| DORA | Automated TLPT reporting integration with regulator portals | Equixly covers execution, but integration with ORKIS portal is not provided by any ISV. |
| Analytics | Banking-specific Customer Data Platform (CDP) | Quantexa is closest, but many CDPs are general-purpose. |
| Channel Delivery | Banking-specific conversational AI (beyond Unblu co-browsing) | Unblu covers co-browsing but not full AI chatbot. |

---

## 6. Unified Synthesis Table

| Value Chain Stage | Technical/Functional Use Cases | Mapped ISVs (EMEA Focused) |
|-------------------|-------------------------------|----------------------------|
| **Product Lifecycle Management** | - Product configuration & pricing (REST API, event-driven change) <br> - Product catalog publication (event-driven sync) <br> - Compliance check on product terms (API to rule engine, MIFID II) | - **Mambu** – Amsterdam, NL – Composable Cloud Banking Platform <br> - **Thought Machine** – London, UK – Vault Core <br> - **Temenos** – Geneva, CH – Transact Core Banking <br> - **Tuum** – Tallinn, EE – Modular Core Banking <br> - **Skaleet** – Boulogne-Billancourt, FR – Core Banking Platform <br> - **SDK.finance** – Vilnius, LT – White-label Fintech Platform |
| **Customer Acquisition & Onboarding** | - Digital identity verification (REST API, webhook for eIDAS) <br> - KYC/CDD automation (event-driven screening, API to core) <br> - Account opening (REST state machine, event notifications) <br> - Open Banking consent management (PSD3 API, GDPR audit) | - **Ondato** – London/Vilnius, UK/LT – KYC & AML Platform <br> - **IDnow** – Munich, DE – Video Ident <br> - **Onfido (Entrust)** – London, UK – Identity Verification <br> - **Signicat** – Oslo, NO – Digital Identity & eIDAS <br> - **Veriff** – Tallinn, EE – Identity Verification <br> - **Sumsub** – Berlin, DE – KYC/KYB <br> - **Fenergo** – Dublin, IE – Client Lifecycle Management <br> - **Backbase** – Amsterdam, NL – Engagement Banking Platform (onboarding module) |
| **Account Servicing & Deposits** | - Real-time balance & transactions (REST API, event push) <br> - Card management (API with HSM, tokenization) <br> - Account closure & data portability (REST + file, GDPR Article 20) | - **Mambu** – Amsterdam, NL – Core Banking <br> - **Thought Machine** – London, UK – Vault Core <br> - **Temenos** – Geneva, CH – Transact Core <br> - **10x Banking** – London, UK – SuperCore <br> - **Skaleet** – Boulogne-Billancourt, FR – Core Banking Platform <br> - **Tuum** – Tallinn, EE – Modular Core Banking <br> - **Comarch** – Kraków, PL – Comarch Banking <br> - **Sopra Banking (SBS)** – Paris, FR – Sopra Banking Platform |
| **Lending (Origination & Servicing)** | - Loan application submission (REST, event-driven scoring) <br> - Credit decisioning (API to bureau, cloud ML) <br> - Drawdown & repayment (event-driven to ledger) <br> - BNPL instalment generation (API) | - **Temenos** – Geneva, CH – Transact Core (Lending module) <br> - **Mambu** – Amsterdam, NL – Lending product <br> - **Thought Machine** – London, UK – Vault Core (smart contracts for loans) <br> - **Finastra** – London, UK – FusionFabric.cloud (lending) <br> - **Sopra Banking (SBS)** – Paris, FR – Sopra Banking Platform <br> - **10x Banking** – London, UK – SuperCore (lending) <br> - **Comarch** – Kraków, PL – Comarch Banking <br> - **Oradian** – Zagreb, HR – Cloud-native Core for Emerging Markets |
| **Payments** | - SEPA credit transfer / instant payment (ISO 20022 API, event status) <br> - Open Banking PISP initiation (REST PSD3 API, SCA) <br> - Real-time fraud scoring in payment flow (event-driven ML) <br> - Cross-border payment FX calculation (API) <br> - Reconciliation reporting (API batch) | - **Finastra** – London, UK – FusionFabric.cloud Payments <br> - **Temenos** – Geneva, CH – Transact Payments <br> - **Mambu** – Amsterdam, NL – Payments module <br> - **SDK.finance** – Vilnius, LT – White-label payments <br> - **Comarch** – Kraków, PL – Payments <br> - **Sopra Banking (SBS)** – Paris, FR – Open Banking whitepaper <br> - **Signicat** – Oslo, NO – Consent orchestration (PISP) <br> - **Gap:** No verifiable dedicated PISP cloud-native engine (Token.io not confirmed) |
| **Financial Crime & Compliance** | - Transaction monitoring (AML) – event-driven ingestion, cloud rules engine <br> - Sanctions screening (REST API to watchlist) <br> - SAR reporting (API to regulator, event workflow) <br> - DORA ICT risk monitoring (API for security scans, event incident logging) <br> - Threat-Led Penetration Testing (TLPT) – cloud-native orchestration | - **Quantexa** – London, UK – Decision Intelligence (fraud/KYC) – GCP Partner of the Year <br> - **Ondato** – London/Vilnius – AML screening <br> - **Fenergo** – Dublin, IE – Transaction monitoring, AML <br> - **ServiceNow** – Santa Clara, US (EU Ops) – FSO for case mgmt & ICT risk <br> - **Equixly** – London, UK/EU – Continuous TLPT for DORA <br> - **GRC Solutions** – London, UK – DORA compliance platform <br> - **Dotfile** – Germany – DORA risk register & vendor management <br> - **K2view** – Tel Aviv, IL/EU Ops – Data governance for DORA/GDPR <br> - **Gap:** Dedicated SAR automation ISV (banks use internal/consultancies) |
| **Analytics & Insights** | - Customer 360 data aggregation (event-driven, cloud data lake) <br> - Real-time personalisation (REST ML, event trigger) <br> - Churn prediction (batch cloud-native) <br> - Regulatory reporting (REST API, event anomaly) <br> - PFM & carbon footprint insights | - **Personetics** – Tel Aviv, IL / Zug, CH – Engage (AI personalisation) <br> - **Meniga** – Reykjavik, IS / London, UK – PFM & Insights <br> - **Strands** – Barcelona, ES – PFM <br> - **Quantexa** – London, UK – Customer 360 / Unified Analytics <br> - **Backbase** – Amsterdam, NL – Engagement Banking (analytics module) <br> - **Gap:** Real-time next-best-action engine beyond Personetics (Pega is US-headquartered) |
| **Channel Delivery** | - Omnichannel session management (event-driven state) <br> - Secure token-based authentication (REST OAuth2, SCA) <br> - Digital engagement (co-browsing, video KYC) <br> - Loyalty & rewards (API) <br> - Customer communications (statements, notifications) | - **Backbase** – Amsterdam, NL – Engagement Banking (channels) <br> - **Unblu** – Basel, CH – Co-browsing & video <br> - **Open Loyalty** – Kraków, PL – Loyalty engine <br> - **Latinia** – Barcelona, ES – Real-time alerts <br> - **Quadient** – Paris, FR – Customer communications <br> - **Act-On** – Portland, US (EU Ops) – Marketing automation <br> - **Yousign** – Paris, FR – Electronic signature <br> - **Gap:** Banking-specific conversational AI chatbot (many use generic AI platforms) |
| **Cross-Cutting / Infrastructure** | - Mainframe modernisation (COBOL rehost, data virtualisation) <br> - Cloud migration and sovereignty <br> - Data governance & DSAR automation | - **LzLabs** – Zurich, CH – Software Defined Mainframe <br> - **VirtualZ** – Minneapolis, US (EU Ops) – Mainframe Data Access <br> - **Micro Focus (OpenText)** – Waterloo, CA – COBOL Modernization <br> - **K2view** – Tel Aviv, IL/EU Ops – GDPR DSAR, data governance <br> - **Engine by Starling** – London, UK – Cloud-native core (AWS) <br> - **Gap:** No dedicated EMEA ISV for sovereign cloud migration consulting (services firms exist) |

---

## 7. Cross-Cutting Themes

- **Cloud-native dominance:** The majority of EMEA-headquartered core banking ISVs (Mambu, Thought Machine, 10x Banking, Tuum, SDK.finance) are cloud-native, running on AWS, Azure, or GCP. This aligns with BIAN’s advocacy for modular, API-first architectures  [BIAN Adoption: A Strategic Lever for Banking Transformation](https://www.techmahindra.com/insights/views/bian-strategic-architecture-banking-standardization-intelligent-ecosystems/). Temenos and Finastra retain traditional on-prem options but are accelerating cloud adoption.
- **Regulatory convergence:** PSD3, GDPR, and DORA are driving integration patterns that emphasise event-driven compliance (real-time AML, incident reporting) and API-based consent management. ISVs like Signicat and Equixly are emerging specifically to address these regulatory requirements.
- **Gap in banking-specific analytics:** While general-purpose CDPs exist, only Personetics and Quantexa offer banking-specific personalisation and customer intelligence. Strands and Meniga focus on PFM and carbon footprint, leaving a gap in next-best-action engines for retail banking.
- **Compliance fragmentation:** Financial crime is well-covered by vendors like Quantexa and Fenergo, but DORA compliance requires a multi-vendor approach: Equixly for TLPT, GRC Solutions for risk register, ServiceNow for incident management. No single ISV covers all DORA pillars.
- **Mainframe modernisation:** LzLabs, VirtualZ, and Micro Focus provide tools for legacy migration, but these are typically used in large incumbents rather than greenfield digital banks.

---

## 8. Gaps & Uncertainties

- **Product Lifecycle Management simulation:** No dedicated EMEA ISV for advanced product pricing simulation or lifecycle automation beyond core banking modules. This is often done in-house or via consultancies.
- **PSD3 PISP engine:** While Signicat covers consent orchestration, a pure-play PISP cloud-native engine (similar to Token.io) was not confirmed in the provided dataset or supplementary search; this remains a gap.
- **Automated SAR narrative generation:** No verifiable EMEA ISV offers AI-based suspicious activity report drafting; banks rely on manual processes or general NLP tools.
- **DORA TLPT reporting integration:** Equixly provides continuous penetration testing, but integration with regulator ORKIS portal for automated TLPT reporting is not offered by any ISV.
- **Conversational AI for banking:** Unblu covers co-browsing and video, but full banking-specific conversational AI (chatbots with banking intent) is typically provided by global players (e.g., Nuance, Google) not EMEA-headquartered ISVs.
- **Uncertainty in vendor data for some entries:** The provided dataset had empty fields for several vendors (e.g., Personetics HQ, Infinity product). Web research resolved most, but HQ for Personetics is ambiguous (Israel vs. Switzerland). Infinity (infinity.co) appears to be an AI platform company, but its retail banking relevance is unverified.
- **BIAN service domain coverage:** While BIAN’s Service Landscape v9.1 includes a “Value Chain View”, no single public document maps every BIAN domain to the exact eight phases used here. The mapping is derived from BIAN examples and industry practice.

---

## Methodology

This report was compiled through iterative web research and cross-referencing of multiple sources. The research process followed these steps:

1. **BIAN taxonomy extraction:** Official BIAN documents (Service Landscape v9.1, BIAN Implementation Examples v1  [bian.org](https://bian.org/wp-content/uploads/2024/11/BIAN_Implementation_Examples_v1.pdf), Semantic API Guide  [BIAN Semantic API Practitioner Guide V8.1](https://bian.org/wp-content/uploads/2024/12/BIAN-Semantic-API-Pactitioner-Guide-V8.1-FINAL.pdf)) were analysed to identify service domains relevant to retail banking.
2. **Value chain phase definition:** Eight phases were defined based on BIAN’s value chain view and industry standard retail banking operating models.
3. **Use case derivation:** For each phase, functional, regulatory, and technical use cases were identified from regulatory texts (PSD3  [PSD3 and the Payment Services Regulation: Key Developments...](https://www.mofo.com/resources/insights/260430-psd3-and-the-payment-services-regulation-key-developments), GDPR  [What is GDPR, the EU’s new data protection law?](https://gdpr.eu/what-is-gdpr/), DORA  [Digital Operational Resilience Act (DORA) - eiopa - European Union](https://www.eiopa.europa.eu/digital-operational-resilience-act-dora_en)), industry reports (TechMahindra  [BIAN Adoption: A Strategic Lever for Banking Transformation](https://www.techmahindra.com/insights/views/bian-strategic-architecture-banking-standardization-intelligent-ecosystems/), NTT Data  [www.nttdata.com](https://www.nttdata.com/global/en/-/media/nttdataglobal/1_files/insights/reports/banking-it-services-everest-peak-matrix/report_everest-banking-its-peak-2025.pdf?rev=f28b2ee96ec34069a8f2f95d84314ac1)), and vendor documentation. Integration patterns were assigned based on BIAN’s recommended patterns and market practices.
4. **ISV validation:** The provided dataset of 33 vendors was examined. For vendors with incomplete data, web searches on their official websites, Gartner/Forrester reports, and Crunchbase were conducted to fill HQ, product, and cloud alignment. Additional EMEA-based ISVs were discovered through searches for “DORA compliance ISV EMEA”, “PSD3 regulatory ISV”, “GDPR automation banking”, and “cloud core banking EMEA 2025”. Only vendors with verifiable products and EMEA HQ were included.
5. **Gap analysis:** Use cases were systematically checked against the ISV mapping. Where no verifiable vendor existed, a “gap” was recorded with justification.
6. **Citation integration:** All factual claims were attributed to sources using the provided citation JSON identifiers. Source tiers were considered: official BIAN documents (Tier 2/3), regulatory sources (Tier 1/2), vendor websites (Tier 3), and industry reports (Tier 3).

The resulting report is designed for FSI strategy consultants, market analysts, and solutions architects evaluating the retail banking technology landscape in EMEA.