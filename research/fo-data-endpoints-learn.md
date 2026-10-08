# Finance and operations (FO) data endpoints and integration options: what Microsoft Learn says

- **Scope:** Only learn.microsoft.com pages. Each claim below has its URL and a quote or close paraphrase from that page. I added no outside knowledge.
- **Compiled:** 2026-09-25 (America/Chicago).
- **"Last updated" dates** are the ones each page shows ("Last updated on YYYY-MM-DD"), captured on 2026-09-25.
- **Labels:** **[GA]**, **[Preview]**, **[Deprecated/Retired]** and **[Status not stated]** show only what the cited page says. Where two pages disagree, the item is marked ⚠️ and listed again in the "Contradictions / uncertainties" section at the end.

---

## 1. Microsoft's official overview of integration and data-access options for FO

### 1a. Integration between finance and operations apps and third-party services ("integration overview")
- **URL:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/integration-overview
- **Last updated:** 2026-03-09
- **Purpose, as stated:** "This article helps architects and developers make sound design decisions when they implement integration scenarios."
- **Every pattern in its table** ("The following table lists the integration patterns that are available."):

  | Pattern | Documentation the page links to |
  |---|---|
  | Power Platform integration | Microsoft Power Platform integration with finance and operations apps |
  | OData | Open Data Protocol (OData) |
  | Batch data API | Recurring integrations; Data management package REST API |
  | Custom service | Custom service development |
  | Consume external web services | Consume external web services |
  | Excel integration | Office integration overview |

- **On-premises:** "For on-premises deployments, the only supported API is the Data management package REST API."
- **Synchronous vs. asynchronous:** Inbound OData is "Synchronous", with Batch = "No". The Batch data API is "Asynchronous", with Batch = "Yes". "Both OData and custom services are synchronous integration patterns."
- **Volume guidance:** "If the volume is more than a few hundred thousand records, use the batch data API for integrations."
- **Power BI:** "Don't use OData for Power BI reports. Use entity store for such scenarios instead."
- **Outbound calls:** Production and sandbox environments "support only secured communication that uses Transport Layer Security (TLS) 1.2 or later."
- **What the table leaves out:** It does not list BYOD, Synapse Link / Fabric link, business or data events, dual-write, virtual entities (except inside "Power Platform integration"), or MCP.

### 1b. Microsoft Power Platform integration with finance and operations apps ("shared data layer")
- **URL:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/power-platform/overview
- **Last updated:** 2026-03-11
- **Mandatory since May 2025:** "Beginning May 1, 2025, all environments for finance and operations apps must have the Power Platform Integration enabled." Environments not linked by then "have the Power Platform Integration automatically enabled."
- **The shared data layer:** "Together, virtual entities, dual-write, business events, and data events make up the shared data layer for the convergence of finance and operations apps and the Dataverse platform."
- **Other capabilities the page says the integration unlocks:**
  - AI capabilities: Copilot Studio, AI Builder and Dataverse. "You must enable the Power Platform integration in the environment to access the services for the AI features."
  - Data archival to Dataverse long-term retention.
  - Add-ins.
- ⚠️ **Stale sentence:** The same page says "Today, the Power Platform admin center doesn't manage finance and operations apps… In the interim, you can unlock features… by using Microsoft Power Platform integration functionality in Lifecycle Services." That conflicts with the newer unified-admin pages in section 3.

---

## 2. Status of BYOD, Export to Data Lake and LCS

### 2a. BYOD (bring your own database) — **[No retirement date set; Microsoft recommends moving off it]**
- **FAQ page:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/azure-synapse-link-transition-faq (last updated 2026-08-31)
  - Question "Is BYOD service retired? Is there a retirement date?"
  - Answer: "While a retirement date for BYOD service hasn't been determined, we recommend that you transition to Synapse Link or Fabric link services. Fabric link service is a new, no-copy, no-ETL solution, which enables you to query your data with SQL similar to a 'read-replica' of your data in Fabric."
- **BYOD feature page:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/analytics/export-entities-to-your-own-database (last updated 2026-01-22)
  - The page carries no deprecation banner. It still documents the feature: export data entities into "their own Microsoft Azure SQL database."
- **Replacement named:** Azure Synapse Link for Dataverse or Fabric link (Link to Microsoft Fabric).
- BYOD is **not** listed on the "Removed or deprecated platform features" page (see 2b).

### 2b. Export to Azure Data Lake (FO add-in) — **[Deprecated Oct 15, 2023 → retired Nov 1, 2024 → permanently stops Nov 30, 2026]**
- **Deprecated article:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/azure-data-lake-ga-version-overview (title "Export to Azure Data Lake (deprecated)", last updated 2026-08-25)
  - "Export to Azure Data Lake was retired on November 1, 2024, and will be permanently stopped on November 30, 2026… Extensions won't be granted after November 30, 2026."
  - "…transition to Link to Microsoft Fabric with low-latency sync by November 30, 2026. Link to Fabric is the recommended replacement."
- **Original feature page:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/finance-data-azure-data-lake (last updated 2026-08-25)
  - "Microsoft announced the deprecation of the Export to Data Lake feature, effective October 15, 2023… you can continue to use it until November 1, 2024."
  - It calls Synapse Link "the successor to the Export to Data Lake feature."
- **Deprecation list:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/fin-ops/get-started/removed-deprecated-features-platform-updates (last updated 2026-08-25)
  - Section "Features removed effective November 2026 – Export to Azure Data Lake deprecated November 30, 2026."
  - Reason: "replace it with Azure Synapse Link for Dataverse." Replaced by another feature? "Yes."
- **Transition FAQ:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/azure-synapse-link-transition-faq
  - The November 30, 2026 stop "applies only to the legacy Export to Data lake environment add-in that you install through… LCS."
  - "The notice doesn't apply to Link to Fabric or Azure Synapse Link for Dataverse. Both services remain supported."
  - "Can I get an extension beyond November 30, 2026? No."
- ⚠️ **Replacement wording differs by page.** The deprecated article names Link to Fabric (low-latency sync) as "the recommended replacement". The deprecation list and the older feature page name Azure Synapse Link. The transition pages present both as valid.

### 2c. Lifecycle Services (LCS) — **[Being replaced by Power Platform admin center; new-project freeze Feb 16, 2026; self-service migration in Preview]**
- **Freeze page:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/lifecycle-services/lcs-project-creation-freeze (last updated 2026-09-22)
  - "Starting February 16, 2026, you can't create new cloud implementation projects in Microsoft Dynamics Lifecycle Services for Dynamics 365 Finance, Dynamics 365 Supply Chain Management, and Dynamics 365 Project Operations. New customers… should use the Microsoft Power Platform admin center."
  - Not affected: "Existing customers who already have active Lifecycle Services projects can continue to use them." Commerce, AX 2012 upgrade projects, on-premises, and tenant-to-tenant migrations still use LCS.
  - Timeline: January 2026 code freeze; February 16, 2026 freeze; "September 2026 | Self-service environment migration available in public preview."
- **Deprecation list:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/fin-ops/get-started/removed-deprecated-features-platform-updates
  - "Feature deprecation effective February 2026 – New Lifecycle Services project creation frozen for new customers."
  - Reason: "Dynamics 365 Lifecycle Services is being replaced by the Microsoft Power Platform admin center as part of the unified admin strategy…" Replaced by: "Yes. Power Platform admin center (PPAC)."
  - Also on this page: "Lifecycle Services features deprecated in August 2022 – As part of the One Dynamics One Platform work effort, the following Lifecycle Services features are deprecated." The list includes Announcements, Configuration and data manager, Process data packages (replaced by DIXF), Environment upgrade, System diagnostics, and others.
- **Self-service migration (preview):** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/lifecycle-services/migrate-lifecycle-services-environments-power-platform-admin-center (title "…(preview)", last updated 2026-09-22)
  - "This feature is in public preview… Microsoft recommends that you migrate sandbox environments first and don't use the feature for production environments."
  - "Migration is a one-way operation."
  - "The database isn't moved."
  - After migration: "Use Azure Pipelines and Power Platform deployment capabilities for ALM and code deployment."
  - Cloud-hosted developer environments: "Not supported. Deploy a Unified Developer Environment…"
- **LCS features not carried into PPAC:** https://learn.microsoft.com/en-us/power-platform/admin/unified-experience/finance-operations-apps-overview (last updated 2026-09-10)
  - Table "Lifecycle Services features not implemented in the Power Platform admin center", with the replacement each row names:

    | LCS feature | Replacement named |
    |---|---|
    | Asset library | "Store software packages in Azure DevOps and directly import to Dataverse. Database backups aren't provided for offline use." |
    | Build environments | "Microsoft Hosted Agents in Azure DevOps" |
    | Business process modeler | "Business process catalog" |
    | Methodology | Dynamics Implementation portal or Azure DevOps |
    | Alert service | "Create a support ticket." |
    | Solution management | Microsoft Marketplace |
    | Task recorder | "Save files locally." |

- **Support requests:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/lifecycle-services/support-migration-to-ppac (last updated 2026-03-10). Search results summarized this as support moving to the PPAC Help + Support experience. I did not read the full page, so treat that summary as unverified.

---

## 3. Unified environment / Power Platform admin center model, and how packages deploy

### 3a. The model
- **Unified admin overview:** https://learn.microsoft.com/en-us/power-platform/admin/unified-experience/finance-operations-apps-overview (last updated 2026-09-10)
  - "…the environment for finance and operations apps is now an application within Power Platform… multiple Dynamics 365 applications… can be installed and hosted in the same Power Platform environment with a Dataverse database."
  - Two runtime URLs: "One for customer engagement apps (Environment URL)" and "One for finance and operations apps (Finance and Operations URL)."
  - Capacity-based model, replacing LCS environment slots.
  - "With the unified experience, customers no longer deploy all-in-one VMs."
  - Backup: "a backup is kept in the cloud and never downloaded as a SQL .bak or .bacpac file."
- **Environment types:** https://learn.microsoft.com/en-us/power-platform/admin/unified-experience/unified-environment-types-and-templates (last updated 2026-07-23)
  - "You manage finance and operations apps in the Power Platform admin center with zero Microsoft Dynamics Lifecycle Services footprint."
  - **UPE** (unified production environment): Production type.
  - **USE** (unified sandbox environment): Sandbox type, for "Testing, UAT, staging, training."
  - **UDE** (unified developer environment): Sandbox type, "Single-developer X++ development", limited to 1 AOS. "UDE replaces the cloud-hosted developer virtual machines (VMs)."
- **Naming:** "One Dynamics One Platform" appears on Learn only in the 2022 LCS deprecation entry quoted in 2c. The current pages use "unified admin experience", "unified environments" and "unified developer experience".
- **Unified developer experience:** https://learn.microsoft.com/en-us/power-platform/developer/unified-experience/finance-operations-dev-overview (last updated 2026-02-02)
  - "The unified developer experience consolidates the disparate developer tools and environments across finance and operations apps and Power Platform…"
  - It names dual-write and virtual tables as the two data synchronization technologies.
- **TechTalk summary:** https://learn.microsoft.com/en-us/dynamics365/guidance/techtalks/finance-operations-unified-admin-experience (last updated 2024-09-17; older)
  - "Over time, more and more management capabilities will be migrated from Microsoft Dynamics Lifecycle Services to the Power Platform admin center."

### 3b. How deployable packages and assets deploy
- **CI/CD page:** https://learn.microsoft.com/en-us/power-platform/developer/unified-experience/finance-operations-pipelines (last updated 2026-04-13)
  - Build: use the Create Deployable Package task version 3 and "Check the box for Create Power Platform Unified Package… Optionally, you can choose to generate a separate Lifecycle Services format package."
  - Release: "Power Platform Tool Installer, Power Platform WhoAmI, Power Platform Deploy Package."
- **Release pipeline tutorial:** https://learn.microsoft.com/en-us/power-platform/admin/unified-experience/tutorial-release-pipeline-azure-devops (last updated 2026-03-24)
  - The nightly build "produces a unified package", which "deploys it by using PowerPlatformPackageDeploy@2" through Test → Pre-Production → Production stages.
- **UDE FAQ:** https://learn.microsoft.com/en-us/power-platform/developer/unified-experience/finance-operations-faq (last updated 2026-07-23)
  - Convert legacy LCS packages: "Locate ModelUtil.exe… Choose the -convertToUnifiedPackage option."
  - "For UDE, we moved on to the Power Platform Unified Package format, but you can still create the fully deployable package from Azure DevOps pipelines."
  - ISV licenses go in the `__License` folder.
- **LCS feature table** (URL in 2c): Asset library → "Store software packages in Azure DevOps and directly import to Dataverse."
- **Not found on Learn in this pass:** specific pages on how Power BI reports, Financial reporting (Management Reporter), or analytics or data-lake assets deploy in unified environments. The WebSearch summary mentioned a Financial reporting limitation for UDE, but I could not open a source page, so it is **not verified**.

---

## 4. What Learn says about each endpoint or technology

### OData data entities — **[Status not stated on page (current, documented feature)]**
- **URL:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/odata (last updated 2026-01-22)
- Endpoint: "The URL for the service root on your system has the following format: [Your organization's root URL]/data."
- "This endpoint exposes all the data entities that you mark as IsPublic… It supports complete CRUD."
- Query options: $filter, $count, $orderby, $skip, $top, $expand ("only first-level expansion is supported") and $select.
- Paging: "maximum page size of 10,000."
- "OData actions added through extensions aren't currently supported."

### Virtual entities in Dataverse — **[Status not stated]**
- **URL:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/power-platform/virtual-entities-overview (last updated 2026-01-22)
- "Finance and operations apps act as a virtual data source in Dataverse. They enable full create, read, update, and delete (CRUD) operations… the data for virtual entities doesn't reside in Dataverse."
- "All Open Data Protocol (OData) entities in finance and operations apps are available as virtual entities in Dataverse."
- Calls go to the "CDSVirtualEntityService web API endpoint of finance and operations apps."
- Security: queries run "in the context of that user", meaning the calling Dataverse user mapped to an FO user.
- Latency: co-locate FO and Dataverse; then "overhead is expected to be less than 30 milliseconds (ms) per call."

### Dual-write — **[Status not stated; the separate dual-write async feature is Preview]**
- **Overview:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/dual-write-overview (last updated 2026-04-03)
  - "Dual-write provides tightly coupled, bidirectional integration between finance and operations apps and Dataverse."
  - It is "near-real-time" and supports "Synchronous and bidirectional data flow."
- **Dual-write async:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/dual-write/dual-write-async (title "(preview)", last updated 2026-04-03). I read only the title.

### Azure Synapse Link for Dataverse with FO data — **[GA on stated versions]**
- **URL:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/azure-synapse-link-select-fno-data (last updated 2026-08-03)
- "Use Azure Synapse Link to continuously export data from finance and operations apps into Azure Synapse Analytics and Azure Data Lake Storage Gen2."
- "You can choose both standard and custom finance and operations entities and tables."
- "This feature is generally available with finance and operations application versions" 10.0.36, 10.0.37 or 10.0.38 with the listed cumulative updates.
- Prerequisite: "a finance and operations sandbox (Tier-2) or higher environment. You can also use an environment provisioned with an ERP-based template."
- Cloud-hosted environments: "Microsoft offers limited support for cloud hosted environments (CHE) as of June 1, 2024."

### Link to Microsoft Fabric with FO data — **[Supported; low-latency sync rolling out; SQL analytics endpoint metadata sync in Preview]**
- **Setup page:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/fabric-link-to-data-platform (last updated 2026-09-08)
  - "If your environment is linked to finance and operations apps, you can also select tables from those apps."
  - "Low-latency sync rolls out by station and is enabled automatically."
  - "Higher throughput for finance and operations apps tables, up to 1M or more records per hour per table."
  - Minimum FO builds for low-latency sync: 10.0.47 (7.0.7858.157 / 10.0.2527.192), 10.0.48 (7.0.7996.100 / 10.0.2645.108), 10.0.49 (7.0.8199.19 / 10.0.2790.30).
  - Existing profiles move to low-latency sync only when you "unlink the profile and relink it."
  - "New metadata sync for SQL analytics endpoint (preview)."
- **Comparison page:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/azure-synapse-link-view-in-fabric (last updated 2026-07-20)
  - "Link data from all Dynamics 365 apps, including Dynamics 365 Finance and Operations apps."
  - "Microsoft continues to invest in Link to Fabric as the primary sync path."
- **Change tracking limitation** (transition FAQ, URL in 2a): "Azure Synapse Link or Fabric link enables tables where the 'change tracking' property is enabled. Currently, change tracking can't be enabled for all finance and operations entities."
- **Schema changes** (same FAQ): the ID column becomes `FnO_Id`; soft deletes use `isDelete`; binary fields are removed; "nVarChar(max) fields are included but data is truncated at 2,000 characters."

### Dataverse Web API — **[Status not stated (core platform API)]**
- **URL:** https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/overview (last updated 2026-01-10)
- "The Web API implements the OData (Open Data Protocol), version 4.0."
- The page does not mention FO specifically. FO data reaches Dataverse through virtual entities or dual-write (see above).

### Dataverse TDS (SQL) endpoint — **[Read-only; virtual tables NOT supported]**
- **URL:** https://learn.microsoft.com/en-us/power-apps/developer/data-platform/dataverse-sql-query (last updated 2026-06-01)
- "The Microsoft Dataverse business layer provides a Tabular Data Stream (TDS) endpoint that emulates a SQL data connection. The SQL connection provides read-only access."
- "Only Microsoft Entra ID authentication is supported."
- Ports: 1433 and/or 5558.
- "tables types 'virtual' and 'audit' aren't supported at this time." So FO virtual entities cannot be queried through TDS. Only FO data physically in Dataverse, such as dual-write tables, would appear.

### Business events and data events — **[Status not stated]**
- **Business events:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/business-events/home-page (last updated 2026-01-22)
  - "Business events provide a mechanism that lets external systems receive notifications from finance and operations apps."
  - They are consumed via "Microsoft Power Automate and Azure messaging services."
  - "Don't consider business events as a mechanism for exporting data."
- **Data events:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/business-events/data-events (last updated 2026-06-26)
  - "All standard and custom entities… enabled for Open Data Protocol (OData) can emit data events." These are create, update and delete (CUD) events.
  - "Data events are available only in environments that have the Microsoft Power Platform integration enabled."

### Data management package REST API — **[Status not stated]**
- **URL:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/data-management-api (last updated 2026-04-03)
- "The package API lets you integrate by using data packages. You can use the REST API with both cloud deployments and on-premises deployments."
- Scheduling happens "outside finance and operations apps". Formats: "Only data packages." Protocol: REST. Service type: "OData action."
- Authentication: OAuth 2.0 (Entra ID).

### Recurring integrations — **[Status not stated]**
- **URL:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/recurring-integrations (last updated 2026-01-22)
- "It builds on data entities and the Data management framework… uses secure REST application programming interfaces (APIs)."
- "This feature isn't supported with Dynamics 365 Finance + Operations (on-premises)."
- On the DMF API page, recurring integrations are listed as scheduled inside FO, using files or packages, over SOAP and REST, as a custom service.
- ⚠️ The DMF API page still lists XSLT support for recurring integrations. The deprecation page says "XSLT scripting in Data management" was deprecated in March 2022.

### Custom services — **[Status not stated]**
- **URL:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/custom-services (last updated 2026-06-26)
- "…the service group is always deployed on two endpoints: SOAP endpoint, JSON endpoint."
- JSON endpoint: `https://host_uri/api/services/service_group_name/service_group_service_name/operation_name`
- SOAP endpoint: `https://<baseurl>/soap/services/<Service>?wsdl`

### Official MCP servers

#### Dynamics 365 ERP MCP server (dynamic) — **[GA per release plan, Jan 27, 2026]**
- **Main page:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/copilot-mcp (last updated 2026-08-19; the page carries no preview label)
  - "The Dynamics 365 ERP MCP server provides a dynamic framework for agents to perform data operations and access the business logic of finance and operations apps."
  - Minimum versions: "10.0.47, 10.0.46 PQU-2, 10.0.45 PQU-7."
  - The server feature must be on in Feature Management, and the client must be registered in "Allowed MCP Clients".
  - Environments: "Tier 2 or above, or a Unified Developer Environment. The MCP server isn't supported on Cloud Hosted Environments (CHE)."
  - Tools:
    - Data tools, which work over OData entities: `data_find_entity_type`, `data_get_entity_metadata`, `data_create_entities`, `data_update_entities`, `data_delete_entities`, `data_find_entities`, and `data_find_entities_sql`. The last one "replaces the data_find_entities tool that uses OData in version 10.0.48."
    - Form tools: `form_*`.
    - Action tools: `api_find_actions` and `api_invoke_action`.
  - Security: "The security role of the authenticated user for the agent determines which objects are returned."
  - Licensing for non-Copilot Studio clients: "one copilot credit per 10 tool calls." Finance Premium and SCM Premium are exempt.
  - Limitations include "Language: The MCP server supports only US English (en-us)" and "unavailable during environment downtime."
  - **Static server retiring:** "the 'static Dynamics 365 ERP MCP' server, built on the Dataverse connector framework, has 13 tools… This static server will be retired on October 1, 2026."
- **Release plan:** https://learn.microsoft.com/en-us/dynamics365/release-plan/2025wave2/enterprise-resource-planning/finance-operations-crossapp-capabilities/connect-ai-agents-finance-operations-data-business-logic-expanded-model-context-protocol-server (last updated 2026-08-27)
  - "Public preview: Nov 18, 2025 | General availability: Jan 27, 2026."
- **Endpoint** (VS Code guide): https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/mcp/mcp-vscode
  - "`https://contoso.operations.dynamics.com/mcp`". The Foundry guide uses the same format: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/mcp/mcp-foundry
- **Security:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/mcp/mcp-security (last updated 2026-08-19)
  - "The MCP server is built on the same foundation as the existing API integration framework… the server calls finance and operations APIs by using the user's credentials."
  - The server "doesn't store customer data."

#### Dataverse MCP server — ⚠️ **[GA per release plan, Dec 15, 2025; a Copilot Studio page still says Preview]**
- **Connection page:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-mcp (last updated 2026-06-05)
  - URL: `https://{dataverseOrgName}.crm.dynamics.com/api/mcp`
  - Tools: `search_data`, `search`, `create_record`, `update_record`, `delete_record`, `create_table`, `update_table`, `delete_table`, `read_query` ("Run supported Dataverse SQL SELECT queries"), `describe`, skills tools, and file tools.
  - Billing: "Starting December 15, 2025 Dataverse MCP tools are charged when accessed by AI agents created outside of Microsoft Copilot Studio."
- **Release plan:** https://learn.microsoft.com/en-us/power-platform/release-plan/2025wave1/data-platform/dataverse-mcp-server (last updated 2026-08-27)
  - "Public preview May 20, 2025 | General availability Dec 15, 2025."
  - "only Microsoft Copilot Studio will be enabled by default"; other clients are configured in PPAC.
- **FAQ:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-mcp-faq (last updated 2026-06-05)
  - "The /api/mcp endpoint provides the generally available set… /api/mcp_preview… includes additional preview tools."
  - "The Dataverse MCP server respects Dataverse security roles and row-level security."
- **Configuration:** https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-mcp-disable (last updated 2026-06-05)
- ⚠️ **Conflicting page:** https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-dataverse (last updated 2026-08-03) is titled "Dataverse MCP Server reference (preview)" and says "This is a preview feature." It lists the old tools (`describe_table`, `list_tables`), which the Power Apps page says were removed.
- **Not stated on Learn:** whether the Dataverse MCP server can read FO virtual entities. The TDS page says virtual tables aren't supported by the TDS endpoint. Learn does not say whether `read_query` has the same limit.

---

## 5. Best-practice guidance for choosing among options, including AI agents and Copilot

- **General integration choice:** integration overview (URL in 1a)
  - Real-time, lower volume → OData or custom services.
  - "more than a few hundred thousand records" → batch data API (DMF package API or recurring integrations).
  - Power BI → Entity store, not OData.
- **DMF package API vs. recurring integrations:** decision table on https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/data-management-api, covering scheduling, format, transformation, protocols and service type.
- **Dual-write vs. virtual tables:** Learn training unit https://learn.microsoft.com/en-us/training/modules/get-started-with-powerapps-common-data-service/2b-dual-write-vs-virtual-table (no date shown)
  - Use dual-write for "near-real-time synchronization", "full offline capabilities", and "a tightly integrated and replicated dataset."
  - Use virtual tables to "access external data in real time without duplicating it", for "large datasets", and for "read-heavy scenarios or light CRUD."
- **Shared data layer:** PP integration overview (URL in 1b)
  - "…extension and customization should reduce the amount of data that you copy between databases as much as possible."
- **Analytics and data export:** transition FAQ (URL in 2a)
  - Fabric link for Power BI or Fabric users ("provides the most benefits").
  - Synapse Link incremental exports "if you're using non-Microsoft tools and/or use export to data lake change feeds."
- **AI agents: ERP MCP guidance:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/build-agent-mcp (last updated 2026-03-11)
  - "This article provides guidance and best practices for building an agent by using the MCP server in Microsoft Copilot Studio."
  - Sample instructions: "For create/read/update/delete operations - you MUST prefer using data tools before using form tools."
  - Also: get entity metadata via `data_find_entity_type` before CRUD calls.
  - Model: "The recommended model for agents using the Dynamics 365 ERP MCP server is Claude Sonnet 4.5… If… isn't available… use GPT-5 (Chat)."
- **Data tools vs. form tools:** copilot-mcp page (URL in section 4)
  - Data tools are "more efficient for standard CRUD operations."
  - Form tools are "optimal for… operations… that aren't standard CRUD."
  - Action tools cover logic not reachable through entities or forms.
- **Custom AI tools:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/copilot-ai-plugins (title "…(preview)", last updated 2026-03-05)
  - X++ classes implementing `ICustomAPI` are exposed through the ERP MCP server, or through a Dataverse custom API plus a Copilot Studio tool.
  - "You can develop AI tools… only in the unified developer experience."
  - "This feature is a preview feature."
- **Knowledge-source (Q&A) pattern:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/chat-with-fno-data (title "(preview)", last updated 2026-08-21)
  - "you can configure virtual entities for finance and operations apps as knowledge sources in your agent."
  - Or add a native Dataverse table and sync FO data to it with dual-write.
- **Not found on Learn:** one consolidated decision matrix that compares ERP MCP, Dataverse MCP, virtual entities, OData and Fabric specifically for AI agents.

---

## 6. Does Microsoft document direct SQL or database access to production FO?

**Short answer: No.** Learn says outright that production databases can't be reached over T-SQL or SSMS. Documented database access covers only sandbox and developer environments.

- **BYOD page** (URL in 2a), verbatim:
  > "The application doesn't allow T-SQL connections to the production database. If you're upgrading from a previous version of finance and operations, and you have integration solutions that require direct T-SQL access to the database, BYOD is the recommended upgrade path."
- **Go-live FAQ:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/organization-administration/go-live-faq (last updated 2026-06-18), verbatim:
  > "No. Access to the production environment is limited. You can't access the virtual machine (VM) or Microsoft Internet Information Services (IIS). You also can't access the database through Microsoft SQL Server Management Studio."
  > "Can I request a copy of the backup of my production database? No. However, you can copy your production database to your Tier 2 or higher sandbox environment."
- **Unified environments (UDE/USE only):** https://learn.microsoft.com/en-us/power-platform/developer/unified-experience/finance-operations-product-db-access (last updated 2026-09-10), verbatim:
  > "This feature applies to unified development environments (UDEs) and unified sandbox environments (USEs). The user must have the system administrator (sysAdmin) role in the environment."
  > "In a USE, write access is limited to the db_datawriter database role."
  - Credentials are just-in-time, requested from Visual Studio, restricted to allowed IPv4 addresses, and expire.
- **Unified admin FAQ** (URL in 3a):
  > "How do I access SQL for these environments? You can access the database in developer environments."
- **LCS-managed environments:** https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/database/database-just-in-time-jit-access (last updated 2026-04-03)
  - JIT access is started "From the environment details page for your sandbox environment." The firewall entry "expires after eight hours."
  - The page says JIT "is available for both Lifecycle Services managed environments and Power Platform admin center managed environments." However, the rendered page only contains the LCS sandbox section.
- **Unified admin overview** (URL in 3a):
  > "In Power Platform, a backup is kept in the cloud and never downloaded as a SQL .bak or .bacpac file."
- **Read-only SQL paths to FO data that Learn does document** (none of them is the production FO database):
  - Fabric link SQL analytics endpoint (a "read-replica").
  - Synapse Link data in your own lake.
  - The Dataverse TDS endpoint (Dataverse tables only; virtual tables not supported).
  - BYOD (your own Azure SQL).

---

## Contradictions / uncertainties to flag

1. **Is PPAC managing FO yet?** The PP integration overview (updated 2026-03-11) says "Today, the Power Platform admin center doesn't manage finance and operations apps." The unified admin pages (updated 2026-07/09) describe full PPAC management with "zero… Lifecycle Services footprint." The first page is most likely stale.
2. **Replacement for Export to Data Lake.** The deprecated article names "Link to Fabric" (low-latency sync) as "the recommended replacement." The deprecation list and the older feature page name "Azure Synapse Link for Dataverse." The transition FAQ says both remain supported.
3. **Dataverse MCP status.** The release plan says GA December 15, 2025, and the Power Apps docs carry no preview label. The Copilot Studio reference is titled "(preview)" and lists tools the Power Apps docs say were removed.
4. **ERP MCP action tool names.** The AI tools page says `find_actions` / `invoke_action`. The copilot-mcp page says `api_find_actions` / `api_invoke_action`.
5. **ERP MCP read tool.** `data_find_entities_sql` "replaces the data_find_entities tool that uses OData in version 10.0.48". The server's read path appears to change by version.
6. **Static ERP MCP server retires on October 1, 2026**, six days after this research date. Don't build on it.
7. **Export to Data Lake permanently stops on November 30, 2026.** No extensions.
8. **BYOD** has no retirement date and no deprecation-list entry, but Microsoft recommends moving to Synapse Link or Fabric link.
9. **XSLT.** Deprecated for Data management in 2022, but the DMF API decision table still lists XSLT for recurring integrations.
10. **LCS→PPAC self-service migration** is public preview. Microsoft says not to use it for production during preview.
11. **Not found on Learn:**
    - How Power BI reports, Financial reporting, analytics or data-lake assets deploy in unified environments.
    - Whether the Dataverse MCP server can query FO virtual entities.
    - A single AI-agent decision matrix across all options.
