## ADDED Requirements

### Requirement: Play workspace supports browser-driven smoke orchestration
The dashboard SHALL expose a stable browser automation path for the Play workspace that allows an end-to-end test to create or select a session, submit a prompt, and observe when the resulting job reaches a terminal state.

The automation path SHALL rely on stable labels, roles, or explicit test selectors for the controls required by that smoke flow rather than incidental DOM structure.

#### Scenario: Browser test can submit a prompt
- **WHEN** a browser automation client opens the Play workspace and creates or selects a session
- **THEN** it SHALL be able to locate the prompt input and submit control through stable automation-facing selectors or accessible labels

#### Scenario: Browser test can observe terminal job state
- **WHEN** a submitted prompt job completes, fails, or is cancelled
- **THEN** the Play workspace SHALL expose a stable visible state that allows browser automation to detect that the job is no longer streaming
