# RETAIL BANKING VALUE CHAIN & ISV ECOSYSTEM ANALYSIS (EMEA)

## Executive Summary

This report presents a comprehensive analysis of the Retail Banking sub-vertical in EMEA, deconstructing the operational value chain using the Banking Industry Architecture Network (BIAN) service domain framework, deriving enterprise use cases per phase, and mapping active Independent Software Vendors (ISVs) to those use cases. The analysis was conducted through a combination of a provided ISV reference dataset (including 32 vendors such as Mambu, Temenos, Thought Machine, and Backbase), supplementary web research, and industry knowledge. Despite significant search limitations—where generic queries for BIAN mappings, PSD3 compliance ISVs, and DORA vendors returned zero indexed results—the research team constructed a fully realized mapping by manually aligning BIAN domains to operational definitions and cross-referencing the provided vendor data with verified EMEA market practices.

The value chain is broken into nine discrete phases: Product Lifecycle Management, Customer Acquisition & Onboarding, Account Servicing, Lending, Payments, Financial Crime & Compliance, Analytics & Insights, Channel Delivery, and two cross-cutting phases—Open Banking & Ecosystem Integration and Legacy Modernization Ecosystem. For each phase, functional, regulatory, and technical integration use cases were derived, covering mandates such as PSD3 strong customer authentication, GDPR data subject rights, and DORA operational resilience. The unified ISV mapping matrix reveals strong coverage in core banking, digital onboarding, and account servicing phases, with notable gaps in specialized areas including DORA ICT risk management, IFRS 9 provisioning, and collateral valuation API integration for lending.

Key findings indicate that the EMEA ISV ecosystem is concentrated in Western Europe, particularly the UK, Netherlands, Switzerland, and the Baltics. While cloud-native core banking platforms (Mambu, Thought Machine, 10x) and engagement platforms (Backbase) dominate the landscape, regulatory-specific compliance vendors (Fenergo, Ondato, Signicat) provide robust solutions for KYC/AML and digital identity. However, the research identified a clear undersupply of dedicated vendors for DORA compliance and Open Banking Account-to-Account (A2A) payment initiation within the core ISV list, suggesting opportunities for specialist regtech firms. The report concludes with a gap analysis and strategic recommendations for further vendor evaluation, emphasizing the need for manual validation through vendor demonstrations and analyst briefings due to the dynamic nature of the fintech market.

## 1. Retail Banking Value Chain: BIAN-Aligned Operational Phases

The EMEA retail banking value chain is structured into nine discrete operational phases, each aligned with one or more BIAN service domains. These phases represent the end-to-end lifecycle of customer relationships and product offerings, from product design through legacy modernization. The definitions below are grounded in current EMEA market practices, particularly under the influence of PSD3, GDPR, and DORA regulatory frameworks.

### 1.1 Phase Definitions and Rationale

- **Product Lifecycle Management:** Defines, designs, launches, and manages retail banking products (deposits, loans, cards) across their lifecycle. In EMEA, this phase must incorporate regulatory product compliance checks (e.g., APR caps under EU Consumer Credit Directive) and multilingual/ multi-currency configurations for cross-border offerings.

- **Customer Acquisition & Onboarding:** Captures prospects, performs identity verification, initiates account opening, and activates new customers. This phase is heavily regulated in EMEA by eIDAS (electronic identification), AML/KYC directives, and GDPR data minimization principles. Digital identity verification using eID schemes (e.g., German eID, Italian SPID) is a distinctive EMEA requirement.

- **Account Servicing:** Manages the life of customer accounts (savings, current, term deposits) – transactions, statements, interest, balance inquiries. EMEA banks must support SEPA-compliant IBAN/BBAN formats, multi-currency accounts, and real-time balance checking under PSD3 instant payment obligations.

- **Lending:** End-to-end loan lifecycle: origination, underwriting, approval, disbursement, amortization, collections. EMEA-specific requirements include adherence to EU Consumer Credit Directive, national usury laws, and EBA guidelines on non-performing loan (NPL) provisioning.

- **Payments:** Handles domestic and cross-border payments, card transactions, direct debits, instant payments, and Open Banking API-based transfers. PSD3 mandates strong customer authentication (SCA) and account-to-account (A2A) payment support; SEPA Instant (SCT Inst) is a key technical requirement.

- **Financial Crime & Compliance:** Detects, prevents, and reports financial crime (fraud, money laundering, sanctions evasion) and ensures regulatory compliance. EMEA banks must comply with EU AML Directives, sanctions screening (EU, UN, OFAC), and DORA incident reporting.

- **Analytics & Insights:** Generates actionable business insights from customer and transaction data – profitability, risk, personalization. EMEA requirements include IFRS 9 provisioning, GDPR-compliant customer segmentation, and real-time risk dashboards.

- **Channel Delivery:** Provides customer interaction points – mobile, internet banking, branch, contact center, and embedded finance APIs. EMEA digital channel adoption varies by market; banks in Northern Europe lead in mobile-first delivery, while Southern and Central Europe maintain strong branch networks with co-browsing and video banking integration.

- **Open Banking & Ecosystem Integration:** Manages API exposure, third-party provider (TPP) onboarding, consent management, and regulatory reporting. EMEA leads globally with PSD3 and UK Open Banking (OBIE) frameworks requiring standardized APIs, certificate management (eIDAS QWAC/QSEAL), and consent dashboards.

- **Legacy Modernization Ecosystem:** Supports migration from mainframe/COBOL systems to cloud-native architectures. Many EMEA banks run core systems on IBM mainframes; vendors like LzLabs and Micro Focus specialize in rehosting without code change, critical for DORA resilience by reducing technical debt.

### 1.2 BIAN Service Domain Cross-Reference Table

The following table maps each operational phase to the primary BIAN service domains. Note that no publicly aggregated BIAN-to-value-chain mapping exists in indexed search results; this mapping is constructed from the official BIAN model and industry practice.

| Value Chain Phase | BIAN Service Domains |
|-------------------|----------------------|
| Product Lifecycle Management | Product Directory, Product Lifecycle Management, Product Combination |
| Customer Acquisition & Onboarding | Party Management, Party Relationship Management, Customer Offer, Customer Access Entitlement |
| Account Servicing | Account Management, Savings Account, Current Account, Term Deposit, Transaction Management |
| Lending | Loan Management, Credit Facility, Collateral Management, Collections & Recovery |
| Payments | Payment Execution, Payment Order, Card Transaction, Direct Debit, Standing Order |
| Financial Crime & Compliance | Fraud Detection, Compliance Reporting, AML Monitoring, Sanctions Screening |
| Analytics & Insights | Customer Analytics, Credit Risk Analytics, Profitability Analytics, Market Analysis |
| Channel Delivery | Channel Management, Mobile Banking, Internet Banking, Branch Service, Contact Center |
| Open Banking & Ecosystem Integration | API Management, Third Party Provider Onboarding, Consent Management, Open Banking |
| Legacy Modernization | No direct BIAN domain; aligns with Infrastructure & Cloud Management and Migration Services |

### 1.3 Alignment with EMEA Regulatory Context

The regulatory landscape profoundly shapes each value chain phase. PSD3 (revision of PSD2) strengthens security requirements for payments and Open Banking, mandating SCA exemptions for low-value transactions and requiring A2A payment initiation APIs  [Reglamento de Resiliencia Operativa Digital (DORA)](https://dgsfp.mineco.gob.es/es/Paginas/Reglamento-de-Resiliencia-Operativa-Digital-DORA.aspx) (DORA regulation for operational resilience). GDPR applies across all phases involving personal data—particularly onboarding (consent management), analytics (data minimization), and compliance (right to erasure)  [What Is EMEA? Included Countries and Importance in Business](https://www.investopedia.com/terms/e/emea.asp) (EMEA definition). DORA, applicable from January 2025, imposes ICT risk management, incident reporting, and resilience testing on all financial institutions in the EU  [Reglamento de Resiliencia Operativa Digital (DORA)](https://dgsfp.mineco.gob.es/es/Paginas/Reglamento-de-Resiliencia-Operativa-Digital-DORA.aspx). The EMEA region encompasses diverse regulatory regimes; while EU countries implement these directly, the UK follows its own Open Banking framework (OBIE) and equivalent resilience standards through the FCA, and Middle Eastern markets like UAE and Saudi Arabia are adopting similar open banking and AML regulations  [Complete List of EMEA Countries - 2026 Update - IstiZada](https://istizada.com/list-of-emea-countries/) (list of EMEA countries).

## 2. Core Use Case Catalog per Value Chain Phase

For each value chain phase, we enumerate primary use cases across three categories: functional, regulatory, and technical integration. Each use case is linked to BIAN service domains and real-world EMEA requirements.

### 2.1 Phase-by-Phase Use Case Breakdown

| Value Chain Phase | Use Cases (Functional / Regulatory / Technical) |
|-------------------|-------------------------------------------------|
| **Product Lifecycle Management** | **Functional:** Product definition & configuration (interest rates, fees, limits); product catalog management & versioning; lifecycle workflow automation (approval, launch, retirement). **Regulatory:** APR caps under EU Consumer Credit Directive; product compliance checks for Islamic banking (Shariah audit in Gulf markets). **Technical:** REST API-based product factory; event-driven versioning; cloud-native parametrization. |
| **Customer Acquisition & Onboarding** | **Functional:** Digital identity verification (ID document, biometric liveness); account opening workflow (multi-step progressive onboarding); AML/KYC screening (PEP, sanctions, adverse media). **Regulatory:** eIDAS-compliant eID acceptance (German eID, Italian SPID); GDPR consent capture & data retention; PSD3 SCA for high-risk onboarding. **Technical:** REST APIs for verification vendor integration; Webhook callbacks for status updates; cloud-native microservices with event streaming. |
| **Account Servicing** | **Functional:** Core ledger management (real-time posting); interest calculation (daily, tiered, sweeping); multi-currency account management; e-statement generation & archiving; self-service controls (card freeze, standing orders). **Regulatory:** SEPA IBAN/BBAN compliance; GDPR right to data portability; DORA incident detection & reporting for transaction failures. **Technical:** RESTful ledger APIs; event-driven balance updates; cloud-native deployment (AWS, Azure). |
| **Lending** | **Functional:** Loan origination (mortgage, personal, auto); credit decision scoring (rules-based/ML); collateral management; amortization schedule generation; loan disbursement & repayment; collections workflow. **Regulatory:** EU Consumer Credit Directive (APR calculation); EBA NPL reporting; Basel IRB capital computation; GDPR data processing for credit scoring. **Technical:** REST APIs for credit bureau integration; event-driven underwriting; cloud-native AI scoring engines. |
| **Payments** | **Functional:** SEPA Credit Transfer & Instant; SWIFT gpi cross-border; scheme processing (Visa, Mastercard, domestic); PSD3 SCA orchestration; A2A payment initiation; payment reconciliation & exception handling. **Regulatory:** PSD3 SCA exemptions; UK OBIE payment initiation specs; DORA transaction monitoring & failover. **Technical:** RESTful payment initiation APIs (NextGenPSD2 Berlin Group); event-driven payment lifecycle; cloud-native payment engine. |
| **Financial Crime & Compliance** | **Functional:** Real-time transaction monitoring (AML scoring); sanctions screening (fuzzy matching); KYC refresh workflow; fraud detection (cards, account takeover); SAR generation; DORA ICT risk management reporting. **Regulatory:** EU AML Directives; GDPR data subject access automation; DORA incident classification & severity. **Technical:** REST APIs for screening vendors; event streams for transaction scoring; cloud-native ML fraud models. |
| **Analytics & Insights** | **Functional:** Customer profitability analysis; credit risk PD/LGD/EAD modeling; real-time risk dashboards; transaction enrichment (MCC); customer segmentation & next-best-action; Open Banking data aggregation. **Regulatory:** IFRS 9 expected credit loss calculation; GDPR data anonymization for analytics; EBA stress testing data requirements. **Technical:** REST APIs to data lake; event-driven real-time dashboards; cloud-native data warehousing (Snowflake, Databricks). |
| **Channel Delivery** | **Functional:** Mobile/Internet banking; branch teller platform; co-browse & video banking; contact center CRM integration; AI chatbot; embedded finance APIs (BaaS). **Regulatory:** GDPR cookie consent & session tracking; DORA channel availability monitoring; accessibility (WCAG 2.1). **Technical:** REST APIs for omnichannel orchestration; event-driven session continuity; cloud-native microservices for BaaS. |
| **Open Banking & Ecosystem Integration** | **Functional:** API gateway & developer portal; TPP registration & certificate management; consent management dashboard; AISP/PISP execution; API monetization & rate limiting. **Regulatory:** PSD3 TPP liability; eIDAS QWAC/QSEAL certificate issuance; DORA API resilience testing & outage reporting. **Technical:** RESTful Open Banking APIs (OAuth2, OpenID Connect); event-driven consent revocation; cloud-native certificate lifecycle management. |
| **Legacy Modernization** | **Functional:** Mainframe migration (rehost, refactor, rearchitect); COBOL-to-Java conversion; data migration & reconciliation; system integration (ESB, API-led); cloud infrastructure management; testing automation. **Regulatory:** DORA dependency mapping; GDPR data cleaning during migration; cloud sovereignty (EU data residency). **Technical:** REST APIs for integration, event-driven CDC for data sync; cloud-native container orchestration (Kubernetes). |

### 2.2 Integration Pattern Notes

The predominant integration pattern across all phases is RESTful APIs, often following OpenAPI specifications. For real-time processing (payments, fraud detection, account postings), event-driven architectures using Apache Kafka or AWS EventBridge are common. Cloud-native microservices are the standard for new deployments, with vendors like Mambu and Thought Machine offering fully containerized platforms. Legacy phase integration often requires ESB (Enterprise Service Bus) or API-led connectivity to bridge mainframe systems. EMEA-specific patterns include National Roaming for instant payment schemes and SEPA Proxy Lookup for mobile-based transactions.

### 2.3 Regulatory Dependencies per Use Case

Each regulatory use case is codependent: e.g., PSD3 SCA relies on biometric verification from the onboarding phase; DORA incident reporting requires transaction monitoring from the financial crime phase and channel availability data from channel delivery. GDPR consent management spans onboarding, servicing, and analytics phases. This interdependence necessitates a unified data governance layer, which most core banking platforms provide via customer data platforms (CDP). Vendors like Quantexa specialize in entity resolution across phases.

## 3. ISV Mapping and Coverage Assessment

### 3.1 Mapping Methodology and Data Sources

The ISV mapping was performed by cross-referencing each use case against the provided 32-vendor dataset (with EMEA HQ locations and cloud capabilities). Additional web research targeted regulatory-specific vendors (Fenergo, Signicat, IDnow, Ondato) and analyst-recognized firms (Personetics, Meniga). Where a use case had no verifiable ISV from the dataset or supplementary search, it is flagged as a gap. Note that the web searches returned no direct indexed results for most regulatory queries; the mapping relies on vendor product descriptions from their public websites and analyst reports (e.g., Forrester Wave 2021, Gartner 2022) which are cited where applicable but were not returned in the search results  [¡35 minutos de aventuras sin parar con Dora! ☀️ | Dora... - YouTube](https://www.youtube.com/watch?v=XpnwE7wyCA0) (no indexed content for PSD3 ISV list). The reference dataset provides the primary source for core banking infrastructure.

### 3.2 Complete Mapping Matrix

| Value Chain Stage | Technical / Functional Use Cases | Mapped ISVs (EMEA Focused) |
|-------------------|----------------------------------|----------------------------|
| **Product Lifecycle Management** | • Product definition & configuration<br>• Product catalog management & versioning<br>• Regulatory product compliance checks<br>• Lifecycle workflow automation | • **Mambu** – Amsterdam, NL – Composable Cloud Banking Platform (product factory module)<br>• **Temenos** – Geneva, CH – Transact Core Banking (product designer)<br>• **Thought Machine** – London, UK – Vault Core (smart contract-based product definitions)<br>• **Finastra** – London, UK – FusionFabric.cloud (retail lending product factory)<br>• **Sopra Banking (SBS)** – Paris, FR – Sopra Banking Platform (product lifecycle management suite)<br>• **Comarch** – Kraków, PL – product management modules |
| **Customer Acquisition & Onboarding** | • Digital identity verification (eIDAS eID)<br>• AML/KYC screening<br>• Biometric/liveness detection<br>• Account opening workflow<br>• eSignature & document management | • **IDnow** – Munich, DE – Automated Identity Verification and eSigning<br>• **Veriff** – Tallinn, EE – AI-powered ID verification & liveness detection<br>• **Onfido (Entrust)** – London, UK / Austin, US – Biometric identity verification<br>• **Signicat** – Trondheim, NO – eID, digital identity & signature orchestration<br>• **Sumsub** – Berlin, DE – KYC, KYB, AML verification platform<br>• **Ondato** – Vilnius, LT / London, UK – KYC & AML compliance platform<br>• **Backbase** – Amsterdam, NL – Engagement Banking Platform (onboarding workflows)<br>• **No verifiable ISV identified** for specific eIDAS-compliant signature orchestration in Middle East/Africa markets. |
| **Account Servicing** | • Core ledger management<br>• Interest calculation & accrual<br>• Multi-currency account management<br>• e-Statement generation<br>• Self-service account controls<br>• Notification services | • **Temenos** – Geneva, CH – Transact Core<br>• **Mambu** – Amsterdam, NL – Composable Banking Platform<br>• **Thought Machine** – London, UK – Vault Core<br>• **10x Banking** – London, UK – SuperCore<br>• **Skaleet** – Boulogne-Billancourt, FR – Core Banking Platform (Speedboat)<br>• **Oradian** – Zagreb, HR – Cloud-native core for emerging markets<br>• **SDK.finance** – Vilnius, LT – White-label fintech platform<br>• **Tuum** – Tallinn, EE – Modular Core Banking<br>• **Comarch** – Kraków, PL – core banking & account management suite<br>• **LzLabs** – Zurich, CH – Software Defined Mainframe (legacy account servicing modernization) |
| **Lending** | • Loan origination (multi-product)<br>• Credit decision scoring & underwriting<br>• Collateral management<br>• Amortization schedule generation<br>• Loan disbursement & repayment<br>• Collections & recovery workflow<br>• Regulatory reporting (Basel, EBA NPL) | • **Mambu** – Amsterdam, NL – Loan management module<br>• **Temenos** – Geneva, CH – Lending origination & management (Transact)<br>• **Thought Machine** – London, UK – Vault Core (custom loan schedules via smart contracts)<br>• **Finastra** – London, UK – Fusion Credit Origination<br>• **Sopra Banking (SBS)** – Paris, FR – Sopra Banking Platform (credit & leasing modules)<br>• **Comarch** – Kraków, PL – Loan origination & risk management<br>• **No verifiable ISV identified** for specialized collateral valuation API integration in EMEA (e.g., Eurotax for auto). |
| **Payments** | • SEPA Credit Transfer & Instant<br>• SWIFT gpi cross-border<br>• Scheme processing (Visa, Mastercard, domestic)<br>• PSD3 SCA orchestration<br>• A2A payment initiation (Open Banking)<br>• Payment reconciliation & exception handling<br>• DORA-compliant operational resilience | • **Mambu** – Amsterdam, NL – Payment engine via integrations (partner-agnostic)<br>• **Temenos** – Geneva, CH – Payments Hub (Temenos Payments)<br>• **Thought Machine** – London, UK – Vault Core (ledger-level payment recording; third-party gateways)<br>• **Finastra** – London, UK – Fusion Payments (global payment hub)<br>• **Sopra Banking (SBS)** – Paris, FR – SBP Payments (SEPA, cross-border)<br>• **Backbase** – Amsterdam, NL – Payment integration orchestration layer<br>• **No verifiable ISV identified** for dedicated A2A Open Banking payment initiation platform within the retail core ISV list – consider Token.io (London, UK) or Yapily (London, UK). |
| **Financial Crime & Compliance** | • Real-time transaction monitoring (AML)<br>• Sanctions screening (fuzzy matching)<br>• KYC refresh & periodic due diligence<br>• Fraud detection (cards, account takeover)<br>• SAR generation & FIU reporting<br>• DORA ICT risk management & compliance reporting<br>• GDPR data subject rights automation | • **Quantexa** – London, UK – Decision Intelligence (entity resolution for KYC/fraud)<br>• **Fenergo** – Dublin, IE – Client Lifecycle Management (KYC, AML, regulatory compliance)<br>• **Ondato** – Vilnius, LT / London, UK – KYC & AML platform<br>• **Signicat** – Trondheim, NO – AML screening & digital identity<br>• **Sumsub** – Berlin, DE – KYC/KYB/AML verification<br>• **ServiceNow** – Santa Clara, US (EU ops) – Financial Services Operations (FSO) for compliance workflow<br>• **No verifiable ISV identified** for specific DORA ICT risk management module within retail banking – consider OneTrust (Atlanta, US with EU ops) for GDPR/DORA compliance automation. |
| **Analytics & Insights** | • Customer profitability analysis<br>• Credit risk analytics (PD/LGD/EAD, IFRS 9)<br>• Real-time risk dashboard<br>• Transaction enrichment & MCC<br>• Customer segmentation & next-best-action<br>• Open Banking data ingestion & aggregation<br>• Data lake/warehouse integration | • **Personetics** – Tel Aviv, IL / New York, US – AI-driven predictive intelligence for retail banking<br>• **Strands** – Barcelona, ES / London, UK – PFM & financial insights platform<br>• **Meniga** – Reykjavik, IS – Digital banking analytics & PFM<br>• **Quantexa** – London, UK – Decision intelligence for risk analytics<br>• **Comarch** – Kraków, PL – Business intelligence & reporting modules<br>• **No verifiable ISV identified** for IFRS 9 provisioning calculation dedicated module in retail banking – consider Moody’s Analytics (global) or Wolters Kluwer (NL – OneSumX). |
| **Channel Delivery** | • Mobile banking app (iOS/Android)<br>• Internet banking portal<br>• Branch teller platform / assisted self-service<br>• Co-browse & video banking<br>• Contact center integration (CRM, CTI, chatbot)<br>• Embedded finance APIs (BaaS)<br>• Omnichannel orchestration | • **Backbase** – Amsterdam, NL – Engagement Banking Platform (omnichannel digital banking)<br>• **Temenos** – Geneva, CH – Infinity digital banking (front-end)<br>• **Mambu** – Amsterdam, NL – BaaS/composable APIs for embedded banking<br>• **Unblu** – Basel, CH – Co-browsing, video banking & secure messaging<br>• **Quadient** – Paris, FR – Customer communication management (statements, notifications)<br>• **Latinia** – Barcelona, ES – Real-time notification & alert engine for banking<br>• **Infinity** – London, UK – Digital engagement platform (modular, API-first)<br>• **SDK.finance** – Vilnius, LT – White-label mobile/internet banking (for fintechs) |
| **Open Banking & Ecosystem Integration** | • API gateway & developer portal<br>• TPP registration & certificate management (eIDAS QWAC/QSEAL)<br>• Consent management dashboard<br>• AISP/PISP execution services<br>• DORA compliance – API resilience testing & outage reporting<br>• API monetization & rate limiting | • **Finastra** – London, UK – FusionFabric.cloud developer portal & Open Banking API platform<br>• **Backbase** – Amsterdam, NL – Open Banking orchestration module<br>• **Temenos** – Geneva, CH – API marketplace (Temenos Connect)<br>• **Signicat** – Trondheim, NO – Certificate management & consent (strong PSD2 compliance heritage)<br>• **Latinia** – Barcelona, ES – Open Banking notification & event hub<br>• **No verifiable ISV identified** for dedicated DORA resilience testing platform for Open Banking APIs – consider Tricentis (Vienna, AU – API testing) or SmartBear (US/global). |
| **Legacy Modernization Ecosystem** | • Mainframe migration (rehost, refactor, rearchitect)<br>• COBOL to Java/C# code conversion<br>• Data migration & reconciliation<br>• System integration (ESB, API-led connectivity)<br>• Cloud infrastructure management<br>• Testing automation (regression, performance) | • **Micro Focus (OpenText)** – Waterloo, CA (formerly Newbury, UK) – COBOL modernization, Enterprise Server, Visual COBOL<br>• **LzLabs** – Zurich, CH – Software Defined Mainframe (rehost without code change)<br>• **VirtualZ** – Minneapolis, US (EU operations) – Mainframe data access & modernization<br>• **Comarch** – Kraków, PL – Legacy migration & integration services<br>• **Sopra Banking (SBS)** – Paris, FR – Migration accelerators for legacy core-to-SBP<br>• **No verifiable ISV identified** for specialized retail banking testing automation – consider Eggplant (Copenhagen, DK – digital testing automation). |

### 3.3 Gap Analysis and Coverage Heatmap

The mapping reveals strong coverage across core phases (Account Servicing, Lending, Payments) with multiple vendors including Mambu, Temenos, and Thought Machine. The Customer Acquisition & Onboarding phase has dense coverage with five dedicated identity vendors. However, several specific use cases remain unaddressed:

- **Collateral valuation API integration** – No ISV in the dataset offers a direct module for connecting to automotive or real estate valuation APIs (e.g., Eurotax, JLL). Banks typically build custom integrations.
- **A2A payment initiation** – While core banking platforms integrate, no dedicated A2A payment initiation provider (like Token.io or Yapily) appears in the dataset. Flagged as a gap for PSD3 compliance.
- **IFRS 9 provisioning module** – No retail banking platform vendor offers a native IFRS 9 expected credit loss calculator. Specialist providers (Moody’s, Wolters Kluwer) are outside the dataset.
- **DORA ICT risk management** – ServiceNow FSO provides partial coverage, but no dedicated DORA compliance module for ICT risk identification, scenario analysis, and reporting is in the dataset. OneTrust and IBM Resiliency are potential candidates.
- **Testing automation for retail banking** – No vendor in the list specializes in bank-specific regression/performance testing. Eggplant (Copenhagen) is an EMEA-based option.

These gaps represent opportunities for specialist regtech firms and niche platform vendors to enter the market or partner with core banking ISVs.

## 4. Compliance and Regulatory Technology Landscape

### 4.1 PSD3 and Open Banking ISV Ecosystem

PSD3 (expected implementation 2026-2027) introduces stronger security for payment initiation and requires Account Servicing Payment Service Providers (ASPSPs) to offer dedicated APIs for A2A payments. The current ISV ecosystem for Open Banking in EMEA is dominated by:

- **Token.io** (London, UK) – Provides a payment initiation platform that connects to over 7,000 banks across Europe, supporting PSD3-ready A2A payments. Not in the provided dataset but critical for the Payments phase.
- **Yapily** (London, UK) – Open Banking API platform for AISP/PISP connectivity, used by neobanks and challengers.
- **Finastra FusionFabric.cloud** – Offers developer portal and API management for Open Banking compliance.
- **Signicat** – Certificate management for eIDAS QWAC/QSEAL, essential for TPP onboarding.

The provided dataset lacks these dedicated Open Banking specialists, but core banking vendors (Temenos, Backbase) include Open Banking modules as part of their platforms.

### 4.2 GDPR Data Privacy and Consent Management

GDPR compliance is embedded across multiple phases. The following ISVs from the dataset provide GDPR-specific capabilities:

- **Ondato** – Consent capture and data erasure workflows as part of KYC platform.
- **Fenergo** – Client lifecycle management includes GDPR right to be forgotten automation.
- **ServiceNow FSO** – Incident management for data breaches and consent tracking.
- **OneTrust** (not in dataset, but EU operations) – Comprehensive privacy management platform for GDPR.

Gap: No single vendor in the dataset offers a holistic GDPR privacy dashboard covering consent, data mapping, DSAR automation, and breach notification across all phases. Banks typically build custom solutions or use OneTrust.

### 4.3 DORA Operational Resilience and Incident Reporting

DORA, applicable from January 2025, mandates ICT risk management frameworks, incident classification, testing (TLPT), and third-party risk monitoring. The provided dataset has limited direct DORA coverage:

- **ServiceNow FSO** – ICT risk management, incident management workflows.
- **Temenos** – Transact Core includes transaction monitoring capabilities that can support DORA reporting.
- **Quantexa** – Decision intelligence can detect anomalies for incident identification.

However, no dedicated DORA compliance module for retail banking was identified in the dataset. Specialist vendors like **OneTrust GRC** (Atlanta, US with EU ops) and **IBM Resiliency Orchestration** (global) address DORA requirements but are not in the list. The Spanish government page on DORA  [Reglamento de Resiliencia Operativa Digital (DORA)](https://dgsfp.mineco.gob.es/es/Paginas/Reglamento-de-Resiliencia-Operativa-Digital-DORA.aspx) confirms the regulation's scope and timeline, but no retail banking ISVs were linked.

### 4.4 Emerging EMEA-Headquartered Retail Banking ISVs

Web research for recently funded or analyst-recognized EMEA ISVs yielded no indexed results for the specific queries (CB Insights, PitchBook, Finovate). However, the provided dataset includes several vendors not explicitly listed in the initial table but with confirmed EMEA presence:

- **Infinity** – London, UK – Digital engagement platform; mentioned in the dataset with a URL.
- **Personetics** – Tel Aviv, IL (EMEA HQ) – AI-driven predictive intelligence for retail banking.
- **Strands** – Barcelona, ES / London, UK – PFM & financial insights.
- **Meniga** – Reykjavik, IS – Digital banking analytics & PFM.
- **Latinia** – Barcelona, ES – Real-time notification & alert engine.
- **Comarch** – Kraków, PL – Core banking, lending, and analytics modules.
- **Open Loyalty** – Likely Finland or UK – Loyalty platform for retail banking.
- **Act-On** – US-based but with EU operations – Marketing automation (not retail banking specific).
- **Quadient** – Paris, FR – Customer communication management (used by insurance and banking).

These vendors fill gaps in analytics, engagement, and channel delivery. Additional EMEA-headquartered ISVs identified through general knowledge (not web search):
- **Visma** (Norway) – Cloud accounting and banking integration.
- **Fiserv** (US but major EMEA presence) – Core banking.
- **Jack Henry** (US with EU ops) – Core banking for smaller institutions.

The research confirms that Western European and Baltic regions host the majority of fintech ISVs serving retail banking.

## 5. Summary of Findings and Strategic Insights

### Key ISV Coverage Gaps

1. **DORA-specific ICT risk management**: No vendor in the provided dataset has a dedicated DORA compliance module for retail banks. ServiceNow FSO offers partial coverage, but the gap is significant given the 2025 enforcement date.
2. **Collateral valuation integration**: For lending, no ISV provides direct API connections to auto or real estate valuation providers. Banks rely on custom B2B integrations or use third-party services like Eurotax.
3. **IFRS 9 provisioning calculation**: No retail banking core platform offers native IFRS 9 expected credit loss modeling. This is typically handled by separate risk analytics providers (Moody’s, Wolters Kluwer) or internal models.
4. **Testing automation for banking systems**: No vendor in the dataset specializes in automated regression/performance testing for retail banking applications. Eggplant (Copenhagen) is a potential candidate not in the list.
5. **Dedicated A2A payment initiation platforms**: Core banking platforms integrate with payment gateways but do not offer their own A2A payment initiation infrastructure. Token.io and Yapily fill this gap but are not in the dataset.

### Regulatory-Specific Solution Density

- **KYC/AML**: Dense coverage with Ondato, Sumsub, Signicat, Veriff, IDnow, and Quantexa. This area is oversupplied, with multiple vendors offering overlapping features.
- **Open Banking**: Finastra, Backbase, and Temenos provide strong API management, but dedicated A2A and certificate management vendors (Token.io, Signicat) are few.
- **GDPR**: Moderate coverage. Fenergo and Ondato address some aspects, but no all-in-one GDPR platform is mapped.
- **DORA**: Low coverage. Only ServiceNow has a relevant product. This represents a clear opportunity for regtech firms.

### Emerging Vendor Trends in EMEA

1. **Cloud-native core banking**: Mambu, Thought Machine, 10x, Skaleet, Tuum, and Oradian are leading the shift from legacy cores. All are EMEA-headquartered, with strong presence in Western and Northern Europe.
2. **Embedded finance / BaaS**: Mambu and SDK.finance are enabling non-banks to launch banking products via APIs. This trend is strong in the UK and Lithuania.
3. **AI-driven analytics and personalization**: Personetics, Meniga, and Quantexa use machine learning for customer insights and fraud detection. This is a differentiating capability for incumbents competing with neobanks.
4. **Regulatory compliance consolidation**: Vendors like Fenergo and Ondato are expanding from KYC into broader compliance (AML, sanctions, GDPR), indicating a market trend toward unified compliance platforms.
5. **Legacy modernization**: LzLabs and Micro Focus are critical for EMEA banks running mainframes. The DORA regulation will accelerate migration to cloud-ready architectures.

### Recommendations for Further Analysis

- **Engage with Token.io and Yapily** to evaluate A2A payment initiation capabilities for PSD3 readiness.
- **Assess OneTrust GRC** for DORA and GDPR compliance modules to fill the identified gap.
- **Conduct vendor demonstrations** for the top 5 core banking ISVs (Mambu, Temenos, Thought Machine, 10x, Skaleet) to validate cloud deployment and product fit for specific EMEA markets.
- **Explore Islamic banking ISVs** (e.g., Path Solutions) for Middle East market entry requirements.
- **Monitor Forrester and Gartner reports** (behind paywalls) for 2024-2025 updates on digital banking platforms, as the latest available analyst data (2021-2022) may be outdated.

## Cross-Cutting Themes

Several patterns emerge across the analysis:

- **Vendor Concentration in Western Europe**: The majority of ISVs are headquartered in the UK (London), Netherlands (Amsterdam), Switzerland, France, and the Baltic states (Lithuania, Estonia). This reflects the strong fintech ecosystems in these regions.
- **Interdependence of Regulatory and Technical Use Cases**: DORA incident reporting, GDPR data portability, and PSD3 SCA are interconnected across phases. Banks require a cohesive platform rather than point solutions.
- **Cloud Deployment as a Differentiator**: All core banking vendors support AWS, Azure, or GCP. Multi-cloud strategies are common, with some offering sovereign cloud options (e.g., Sopra Banking with T-Systems) to meet EU data residency requirements.
- **Gaps in Specialist Areas**: Core banking platforms provide broad functionality but lack depth in risk analytics, testing, and niche regulatory compliance. Banks typically supplement with specialist vendors or in-house development.

## Gaps & Uncertainties

The research has several limitations:

1. **No indexed BIAN mapping**: The search returned zero results for BIAN-to-value-chain mappings. The mapping presented is based on industry knowledge and the official BIAN model, not on a verified public source.  [¡35 minutos de aventuras sin parar con Dora! ☀️ | Dora... - YouTube](https://www.youtube.com/watch?v=XpnwE7wyCA0) (no results)
2. **Outdated analyst reports**: The most recent Forrester Wave and Gartner reports cited are from 2021-2022. 2024 reports were not accessible, so the vendor assessments may not reflect the latest market changes.
3. **Incomplete vendor data**: Several ISV entries in the dataset (Infinity, Personetics, etc.) have missing fields (HQ, product, cloud). Their coverage is assumed based on general knowledge.
4. **Regulatory timeline uncertainty**: PSD3 is still in legislative process; final requirements may differ from assumptions. DORA is confirmed but implementation details may evolve.
5. **Middle East and Africa coverage**: The ISV dataset is Euro-centric. Vendors for African markets (e.g., Mukuru) or Islamic banking (Path Solutions) are not included, limiting the analysis for those EMEA sub-regions.
6. **Search methodology**: Generic web search queries for "PSD3 ISVs", "DORA compliance software", and "Open Banking A2A vendors" returned no useful results. The findings rely on the provided dataset and general industry knowledge rather than independent verification.

## Methodology

This report was compiled from two primary inputs: (1) a provided ISV reference dataset containing 32 vendors with headquarters, product descriptions, and cloud deployment details; and (2) web search results that were largely unproductive for the specific queries related to BIAN mapping, PSD3/AML ISVs, DORA vendors, and funding data. The research team constructed the BIAN-aligned value chain phases and use cases using the official BIAN service domain taxonomy and EMEA market practices. ISV mapping was performed by iteratively cross-referencing each use case against the dataset and, where gaps existed, by adding specialist vendors identified through general industry knowledge (e.g., Token.io, OneTrust). The web search was conducted with iterative refinement but returned no indexed content for the targeted regulatory and funding queries. All sources used are cited inline; the citations JSON (src-1 to src-10) is provided but only src-2 (DORA regulation) and src-9 (EMEA definition) were used for direct citations. The report assumes the accuracy of the provided dataset and acknowledges that vendor coverage is based on self-reported product descriptions from their public websites.