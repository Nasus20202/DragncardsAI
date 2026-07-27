## MODIFIED Requirements

### Requirement: Resilient provider and model loading
The dashboard initial load SHALL tolerate a slow or failed providers fetch and unavailable providers without blocking or breaking the rest of the dashboard. A failure in any single initial-load call SHALL degrade gracefully rather than failing the whole dashboard.

The provider catalog SHALL be loaded off the dashboard's blocking initial-load path. The workspace SHALL render as soon as the dashboard configuration, skills, and sessions have resolved, seeded from the configuration defaults, and SHALL NOT wait for the provider catalog before its first paint. The dashboard configuration SHALL remain the only initial-load call whose failure is fatal.

When the provider catalog subsequently arrives, the dashboard SHALL apply it: it SHALL default the provider and model selectors to a working provider so that model selection remains available on providers that work, and it SHALL surface unavailable or failed providers as a non-blocking notice. Applying a late-arriving catalog SHALL NOT overwrite a provider/model selection the user has already edited or one that a loaded session has committed.

#### Scenario: Workspace renders before the provider catalog resolves
- **WHEN** the dashboard loads and the providers fetch is still in flight
- **THEN** the dashboard SHALL render the workspace and report a ready status without waiting for the providers fetch to complete

#### Scenario: Late-arriving catalog is applied
- **WHEN** the providers fetch resolves after the workspace has already rendered
- **THEN** the dashboard SHALL apply the catalog, defaulting the provider and model selectors to a working provider and updating the unavailable-provider notice

#### Scenario: Late-arriving catalog does not clobber an existing selection
- **WHEN** the providers fetch resolves after the user has changed the provider or model, or after a loaded session has committed its own model
- **THEN** the dashboard SHALL leave that selection unchanged

#### Scenario: One failed load call degrades gracefully
- **WHEN** the providers fetch (or any single initial-load call) fails or is slow during dashboard load
- **THEN** the dashboard SHALL still load the remaining data and SHALL NOT present a single fatal error that blocks the workspace

#### Scenario: Unavailable providers surfaced non-blockingly
- **WHEN** one or more providers report that they are unavailable
- **THEN** the dashboard SHALL surface those providers as a non-blocking notice rather than a fatal error

#### Scenario: Selectors default to a working provider
- **WHEN** some providers are unavailable but at least one provider works
- **THEN** the dashboard SHALL default the provider and model selectors to a working provider and SHALL allow the user to select a model on it
