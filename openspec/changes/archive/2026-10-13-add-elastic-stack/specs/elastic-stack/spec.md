# Spec Delta

## Purpose

Defines the dev environment's self-hosted Elasticsearch and Kibana: how they start, authenticate, keep data and stay within a fixed memory budget, so they can receive Fornada's traces, logs and metrics without making the developer's machine unusable.

## ADDED Requirements

### Requirement: Elasticsearch and Kibana run with the dev environment
The dev environment SHALL run a single-node Elasticsearch and a Kibana connected to it, both starting with the other dev services and restarting unless stopped. Their images SHALL be pinned to the same exact Elastic version as the EDOT Collector.

#### Scenario: Dev environment starts
- **WHEN** the dev container is started or rebuilt
- **THEN** Elasticsearch reports a green or yellow cluster health and Kibana reports itself available, alongside `postgres`, Langfuse and the Collector

#### Scenario: Versions match the Collector
- **WHEN** the compose file is inspected
- **THEN** the Elasticsearch, Kibana and EDOT Collector image tags carry the same Elastic version

### Requirement: Kibana is reachable from the host
Kibana SHALL be published on the host's loopback interface on port 5601 and SHALL NOT be bound on any other host interface.

#### Scenario: Kibana opens in the browser
- **WHEN** the maintainer opens http://localhost:5601 on the host with the dev environment running
- **THEN** the Kibana login page loads

#### Scenario: Not exposed beyond the host
- **WHEN** the dev environment is running
- **THEN** port 5601 is bound only on 127.0.0.1

### Requirement: Elasticsearch is reachable only inside the dev network
Elasticsearch SHALL accept HTTP on port 9200, reachable from other dev services by its service name. No Elasticsearch port SHALL be published to the host.

#### Scenario: Reachable by service name
- **WHEN** a client in the `dev` container sends an HTTP request to the Elasticsearch service name on port 9200
- **THEN** Elasticsearch answers

#### Scenario: Not exposed on the host
- **WHEN** the dev environment is running
- **THEN** no Elasticsearch port is bound on the host

### Requirement: Access requires authentication
Elasticsearch SHALL require authentication on every request, and Kibana SHALL require a login. The maintainer SHALL be able to log in to Kibana as the `elastic` superuser with the password from the dev environment secrets.

#### Scenario: Anonymous request rejected
- **WHEN** a client sends a request to Elasticsearch without credentials
- **THEN** Elasticsearch answers 401

#### Scenario: Maintainer logs in
- **WHEN** the maintainer logs in to Kibana as `elastic` with the generated password
- **THEN** Kibana opens its home page

### Requirement: Kibana connects with its own service user
Kibana SHALL connect to Elasticsearch as the built-in `kibana_system` user, not as the superuser. The `kibana_system` password SHALL be set without manual steps before Kibana first connects.

#### Scenario: Fresh environment
- **WHEN** the dev environment starts with an empty Elasticsearch volume
- **THEN** Kibana becomes available without the maintainer running any command

#### Scenario: Restart with existing data
- **WHEN** the dev environment restarts with an existing Elasticsearch volume
- **THEN** Kibana becomes available again with the same credentials

### Requirement: Elastic secrets stay out of the repo and the workspace
The `elastic` password, the `kibana_system` password and Kibana's encryption key SHALL be dev environment secrets, generated randomly and provided only to the Elastic services. They SHALL NOT appear in any committed file and SHALL NOT be passed to the `dev` container.

#### Scenario: Secrets kept out
- **WHEN** the committed compose file and templates are inspected, and the `dev` container's environment is listed
- **THEN** none of them contains an Elastic secret value

#### Scenario: Existing environment gets the new secrets
- **WHEN** the dev container is started on a machine whose dev environment secrets file was created before this change
- **THEN** the Elastic secrets are added to it without changing any other secret

### Requirement: Elasticsearch data persists
Elasticsearch SHALL keep its data in a named volume, so indices and the security configuration survive a container restart or rebuild.

#### Scenario: Restart keeps data
- **WHEN** a document is indexed and the dev environment is restarted
- **THEN** the document is still searchable

### Requirement: Elastic services have a fixed memory budget
Elasticsearch SHALL be limited to 1.5 GiB of RAM and Kibana to 1 GiB, both with no swap. Elasticsearch's JVM heap SHALL be fixed at 512 MiB. When a limit is hit, only that service SHALL be affected.

#### Scenario: Limits applied
- **WHEN** the dev environment is running
- **THEN** the container runtime reports a 1.5 GiB memory limit for Elasticsearch and a 1 GiB limit for Kibana, and Elasticsearch reports a 512 MiB maximum heap

#### Scenario: Machine stays usable with everything up
- **WHEN** every dev service is running and idle after startup, with Kibana open in the browser
- **THEN** Elasticsearch and Kibana each stay under their limit, and the host keeps enough free memory that the editor, the browser and the dev container respond normally
