### **As a**

Infinito.Nexus platform operator

### **I want to**

provide a fully integrated, production-ready Odoo ERP deployment within the Infinito.Nexus ecosystem

### **So that**

organizations can manage finance, CRM, inventory, HR, sales, website, marketing and other ERP workflows directly inside their sovereign Infinito.Nexus installation.

## **Acceptance Criteria**

### ✅ **Deployment**

*   Odoo runs fully containerized via a new `web-app-odoo` Ansible role following the Infinito.Nexus _web-app baseline templates_.
    
*   Docker Compose stack includes:
    
    *   Odoo core container
        
    *   PostgreSQL (managed by database role)
        
    *   Optional Redis cache
        
*   All volumes, env vars, ports and healthchecks follow Infinito.Nexus conventions.
    

### ✅ **Identity Integration**

*   OIDC login available using Keycloak (preferred modern method).
    
*   LDAP login available via OpenLDAP.
    
*   OIDC/LDAP configuration is fully automated via Ansible (env vars, config files, init scripts).
    
*   Admin user is auto-provisioned.
    

### ✅ **Features &amp; Modules**

*   Installation of required core modules:
    
    *   CRM
        
    *   Contacts
        
    *   Sales
        
    *   Accounting
        
    *   Website &amp; Forms
        
    *   Project
        
    *   Inventory
        
    *   HR (optional)
        
*   Additional modules can be toggled via variables:
    
    *   `odoo_modules_enabled: []`
        

### ✅ **CSP &amp; Reverse Proxy**

*   Odoo receives a fully correct Nginx/CSP configuration using:
    
    *   `csp_filters.py`
        
    *   `nginx_vhost` logic
        
*   WebSockets configured for live chat, POS, and bus notifications.
    
*   Supports HTTPS termination and internal service names.
    

### ❇️ **Infinito.Nexus Integration**

*   A new marketplace entry for “Odoo ERP”.
    
*   Dynamic application menu integration via tags:
    
    *   `erp`, `odoo`, `business`, `crm`, `finance`, `inventory`
        
*   Automatic URL generation for desktop and mobile launchers.
    
*   Centralized backup handling via existing backup roles.
    

## **Definition of Done**

*   A fully functional `web-app-odoo` role exists in the repository.
    
*   Odoo deploys successfully with one command on a fresh host.
    
*   Users can log in via OIDC/LDAP.
    
*   Default modules load without errors.
    
*   The app is accessible via the generated domain (e.g., `erp.infinito.nexus`).
    
*   Marketplace entry is visible and categorized.
    
*   Documentation exists in:
    
    *   `roles/web-app-odoo/README.md`
        
    *   Infinito.Nexus Documentation Wiki → ERP Section
        

## **References**

*   Conversation: _“ChatGPT Conversation — Odoo OIDC/LDAP integration for Infinito.Nexus”_
    
*   Internal baseline: `templates/roles/web-app/*`
    
*   Similar roles: `web-app-openproject`, `web-app-taiga`, `web-app-espocrm`