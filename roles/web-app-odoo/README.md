# Odoo ERP

## Description

Deploy [Odoo](https://www.odoo.com/), a powerful open-source ERP suite, within the Infinito.Nexus ecosystem. Manage finance, CRM, inventory, HR, sales, website, marketing, and other business workflows directly inside your sovereign Infinito.Nexus installation.

## Overview

This role automates Odoo deployment in a containerized environment. It configures the Odoo application, PostgreSQL database, optional Redis cache, reverse proxy integration, and identity federation via OIDC (Keycloak) or LDAP (OpenLDAP).

## Purpose

Provide organizations with a fully integrated, production-ready ERP deployment following Infinito.Nexus conventions. Users can manage all critical business processes through a single unified platform.

## Features

- **CRM & Contacts:**
  Manage customer relationships, leads, opportunities, and contact information with powerful pipeline views.

- **Sales Management:**
  Create quotes, track orders, manage pricing, and automate sales workflows from lead to invoice.

- **Accounting & Finance:**
  Handle invoicing, payments, bank reconciliation, and financial reporting with multi-currency support.

- **Inventory & Warehouse:**
  Track stock levels, manage warehouses, automate replenishment, and optimize supply chain operations.

- **Website & Forms:**
  Build websites, landing pages, and web forms integrated with your ERP data.

- **Project Management:**
  Plan projects, assign tasks, track time, and collaborate with team members.

- **HR Management (Optional):**
  Manage employees, leaves, expenses, recruitment, and payroll processes.

- **OIDC Single Sign-On:**
  Integrate with Keycloak for modern OpenID Connect authentication.

- **LDAP Authentication:**
  Connect to OpenLDAP for enterprise directory-based login.

- **Modular Architecture:**
  Enable or disable modules via `odoo_modules_enabled` variable.

## Module Configuration

Configure enabled modules via the role variables:

```yaml
odoo_modules_enabled:
  - crm
  - contacts
  - sale
  - account
  - website
  - project
  - stock
  # - hr  # Optional
```

## Developer Notes

- Access Odoo shell: `container exec {{ odoo_container }} odoo shell -d {{ database_name }}`
- Install modules: `container exec {{ odoo_container }} odoo -d {{ database_name }} -i module_name --stop-after-init`
- Update modules: `container exec {{ odoo_container }} odoo -d {{ database_name }} -u module_name --stop-after-init`

## Credits

Developed and maintained by **Kevin Veen-Birkenbach**.
Learn more at [veen.world](https://www.veen.world).
Part of the [Infinito.Nexus Project](https://s.infinito.nexus/code).
Licensed under the [Infinito.Nexus Community License (Non-Commercial)](https://s.infinito.nexus/license).
