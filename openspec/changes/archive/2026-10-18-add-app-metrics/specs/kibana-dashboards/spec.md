# Spec Delta

## Purpose

Keeps the project's Kibana dashboards as versioned saved objects in the repo and loads them into the dev Kibana, so every environment shows the same views of cost, latency and errors without manual setup.

## ADDED Requirements

### Requirement: Dashboards are versioned in the repo
Every Kibana dashboard the project relies on SHALL be committed as an exported saved-objects file in the repo, together with the data views its panels use. Changing a dashboard SHALL mean changing that file.

#### Scenario: Dashboard in the repo
- **WHEN** a contributor clones the repo
- **THEN** the metrics dashboard and its data view are in a committed saved-objects file

### Requirement: Dashboards load into the dev Kibana on start
On every start of the dev environment, the committed dashboards SHALL be imported into Kibana, overwriting earlier versions of the same objects, without manual steps. The import SHALL use a Kibana user's credentials that stay out of the workspace, and its failure SHALL NOT stop the other services.

#### Scenario: Fresh environment
- **WHEN** the dev environment starts with empty Elastic volumes and Kibana becomes healthy
- **THEN** the metrics dashboard is listed in Kibana without anyone importing it

#### Scenario: Updated dashboard
- **WHEN** the committed file changes and the environment restarts
- **THEN** Kibana shows the new version, with no duplicate dashboard

#### Scenario: Kibana slow to start
- **WHEN** Kibana takes 2 minutes to become healthy
- **THEN** the import waits for it and succeeds, and `dev` is not blocked meanwhile

### Requirement: Metrics dashboard shows cost per conversation
The metrics dashboard SHALL show cost per conversation in US dollars, computed as the sum of `fornada.gen_ai.cost` divided by the sum of `fornada.conversations` over the selected time range, for the service `fornada-api`.

#### Scenario: Known spend
- **WHEN** the API recorded US$ 0.30 of cost and 10 started conversations in the selected range
- **THEN** the panel shows US$ 0.03

### Requirement: Metrics dashboard shows p95 turn latency
The metrics dashboard SHALL show the 95th percentile of `gen_ai.invoke_agent.duration` over time, in seconds.

#### Scenario: Latency spike visible
- **WHEN** a simulator batch runs with chaos mode on and its tool delays slow some turns
- **THEN** the p95 panel rises during that batch

### Requirement: Metrics dashboard shows error rate per tool
The metrics dashboard SHALL show, for each `gen_ai.tool.name`, the share of `fornada.tool.calls` that carry an `error.type`.

#### Scenario: Capacity outages
- **WHEN** a batch with chaos mode on makes `check_capacity` fail in some calls and no other tool fails
- **THEN** the panel shows a non-zero rate for `check_capacity` and zero for the other tools called

### Requirement: Metrics dashboard splits by model and persona
The metrics dashboard SHALL let the viewer filter or split its panels by `gen_ai.request.model` and by `fornada.simulator.persona.id`.

#### Scenario: Cost per persona
- **WHEN** the viewer filters the dashboard to persona `pechincheira`
- **THEN** every panel shows only measurements with `fornada.simulator.persona.id` = `pechincheira`
