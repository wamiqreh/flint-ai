# Branding Research & Recommendation

> **Historical note**: This document was written when the project was still called "Agent Queue Orchestrator." The project has since been rebranded to **Flint**. It is preserved here for historical context.

> A comprehensive analysis of the rebrand from "Agent Queue Orchestrator" to **Flint**.

---

## 1. Why Rebrand?

"Agent Queue Orchestrator" accurately described what the project does — but accuracy and brandability are different things. Here's why a rebrand deserved serious consideration:

### Length & Complexity
- **"Orchestrator" alone is 5 syllables.** The full name was 9 syllables — far too many for casual conversation, documentation headers, or CLI usage.
- Typing `agent-queue-orchestrator` as a command or package name was tedious and error-prone.
- Competitors with shorter names enjoy an inherent discoverability and recall advantage.

### Memorability & Brandability
- The name was **descriptive, not distinctive**. It read like a category label ("a queue orchestrator for agents") rather than a product name.
- It was nearly impossible to build community identity around. Nobody says "I'm an Agent Queue Orchestrator user" — it's too much of a mouthful.
- There was no natural shortened form that felt intentional. "AQO" is pronounceable but doesn't carry meaning on its own.

### Verb Potential
- Great developer tools become verbs: "Docker it," "Grep that," "Curl the endpoint."
- "Let me orchestrator that" doesn't work grammatically. "Let me AQO that" is forced.
- A short, punchy name unlocks this organic adoption pattern.

### Community & Ecosystem
- Hard to create hashtags, Discord server names, or conference talks around.
- Merchandise and swag design is difficult with long names.
- SEO competes with every other "orchestrator" product in the cloud-native space.

### The Bottom Line
The current name tells you what it does. A great brand name makes you *want* to use it.

---

## 2. Naming Criteria

Any candidate name should be evaluated against these requirements:

| Criterion | Target | Weight |
|---|---|---|
| **Length** | 1–2 words, 2–3 syllables max | Critical |
| **Memorability** | Easy to recall after one encounter | Critical |
| **Uniqueness** | Not easily confused with existing tools | Critical |
| **CLI ergonomics** | Comfortable to type 50+ times/day (`<name> init`, `<name> dev`) | High |
| **Package availability** | Not taken on PyPI, npm, NuGet, Docker Hub | High |
| **Evocative meaning** | Suggests flow, orchestration, queuing, agents, reliability | Medium |
| **Domain availability** | .dev, .io, or .com obtainable | Medium |
| **Global-friendly** | No negative connotations in major languages | Medium |
| **Verb potential** | Can be used naturally as a verb | Nice-to-have |
| **Visual identity** | Lends itself to a strong logo/icon | Nice-to-have |

### What the Name Should Evoke
- **Flow** — smooth, continuous movement of tasks
- **Orchestration** — coordination of many parts into a whole
- **Queuing** — ordered, reliable processing
- **Agents** — autonomous workers executing tasks
- **Reliability** — dependable, always-on infrastructure

---

## 3. Name Candidates

### 3.1 Flow Metaphors

#### FlowForge
| Attribute | Detail |
|---|---|
| **CLI form** | `flowforge init`, `flowforge dev` |
| **Tagline** | "Forge your agent workflows" |
| **Pros** | Evokes both flow and creation; strong visual identity (anvil + stream) |
| **Cons** | 2 words / 2 syllables each = feels slightly long; "FlowForge" is an existing Node-RED platform |
| **Availability** | ⚠️ Likely conflicts — FlowForge is an active product (now FlowFuse) |

#### AgentFlow
| Attribute | Detail |
|---|---|
| **CLI form** | `agentflow init`, `agentflow dev` |
| **Tagline** | "Let your agents flow" |
| **Pros** | Directly communicates purpose; intuitive |
| **Cons** | Generic; long to type (9 chars); many "AgentFlow" references exist in AI/ML space |
| **Availability** | ⚠️ Highly likely to conflict on multiple registries |

#### PipeFlow
| Attribute | Detail |
|---|---|
| **CLI form** | `pipeflow init`, `pipeflow dev` |
| **Tagline** | "Pipeline your agents" |
| **Pros** | Short-ish; evokes Unix pipes and data flow |
| **Cons** | Sounds like a plumbing product; "pipe" is overloaded in dev tooling |
| **Availability** | ⚠️ PipeFlow exists in fluid dynamics software |

#### RunFlow
| Attribute | Detail |
|---|---|
| **CLI form** | `runflow init`, `runflow dev` |
| **Tagline** | "Run it. Flow it." |
| **Pros** | Action-oriented; "run" is natural in dev contexts |
| **Cons** | Somewhat generic; doesn't stand out |
| **Availability** | ⚠️ RunFlow exists as a workflow automation tool |

### 3.2 Queue Metaphors

#### QueuePilot
| Attribute | Detail |
|---|---|
| **CLI form** | `queuepilot init`, `qp dev` |
| **Tagline** | "Pilot your queues" |
| **Pros** | Clear meaning; "pilot" implies control and guidance |
| **Cons** | Long (10 chars); hard to abbreviate naturally; "-Pilot" suffix is trendy and may age poorly |
| **Availability** | Likely available but may collide with GitHub Copilot branding patterns |

#### Qonductor
| Attribute | Detail |
|---|---|
| **CLI form** | `qonductor init`, `qonductor dev` |
| **Tagline** | "Conduct your agent orchestra" |
| **Pros** | Clever Q-for-queue substitution; orchestra metaphor is strong |
| **Cons** | Misspelling feels gimmicky; hard to search for; 3 syllables |
| **Availability** | Probably available but spelling confusion is a real adoption barrier |

#### Qraft
| Attribute | Detail |
|---|---|
| **CLI form** | `qraft init`, `qraft dev` |
| **Tagline** | "Craft queues with precision" |
| **Pros** | Short (5 chars); punchy; Q-start is distinctive |
| **Cons** | Pronunciation ambiguity (kraft? kw-raft?); "craft" is overused in dev tools |
| **Availability** | ✅ Likely available — uncommon spelling |

### 3.3 Agent Metaphors

#### Foreman
| Attribute | Detail |
|---|---|
| **CLI form** | `foreman init`, `foreman dev` |
| **Tagline** | "Your agents' foreman" |
| **Pros** | Strong metaphor (overseer of workers); 2 syllables; authoritative feel |
| **Cons** | ⛔ `foreman` is an established Ruby/Rails process manager; loaded gender connotations |
| **Availability** | ❌ Major conflict — Foreman is a well-known DevOps tool |

#### Dispatch
| Attribute | Detail |
|---|---|
| **CLI form** | `dispatch init`, `dispatch dev` |
| **Tagline** | "Dispatch your agents" |
| **Pros** | Perfect metaphor (dispatching workers); works as a verb; professional tone |
| **Cons** | Common word; many projects use "dispatch" in some form; 2 syllables |
| **Availability** | ⚠️ Likely taken on major registries; common term |

#### AgentForge
| Attribute | Detail |
|---|---|
| **CLI form** | `agentforge init`, `agentforge dev` |
| **Tagline** | "Forge autonomous workflows" |
| **Pros** | Strong imagery; implies creation and strength |
| **Cons** | 10 chars to type; "forge" suffix is trending and may saturate |
| **Availability** | ⚠️ AgentForge exists as an AI agent framework |

### 3.4 Workflow Metaphors

#### DagForge
| Attribute | Detail |
|---|---|
| **CLI form** | `dagforge init`, `dagforge dev` |
| **Tagline** | "Forge your DAGs" |
| **Pros** | Technical credibility (DAG = directed acyclic graph); appeals to data engineers |
| **Cons** | Too niche; alienates non-technical users; "DAG" not universally known |
| **Availability** | ✅ Likely available — very specific term |

#### ChainLink
| Attribute | Detail |
|---|---|
| **CLI form** | `chainlink init`, `chainlink dev` |
| **Tagline** | "Link your agent chains" |
| **Pros** | Strong visual metaphor; implies connection and strength |
| **Cons** | ⛔ Chainlink is a major blockchain/oracle project |
| **Availability** | ❌ Major conflict — Chainlink (LINK) is a top-50 cryptocurrency |

#### StepWise
| Attribute | Detail |
|---|---|
| **CLI form** | `stepwise init`, `stepwise dev` |
| **Tagline** | "Orchestration, step by step" |
| **Pros** | Implies methodical, reliable processing; friendly tone |
| **Cons** | Sounds like a tutorial platform, not an infrastructure tool; 2 syllables but 8 chars |
| **Availability** | ⚠️ StepWise exists in several contexts (education, analytics) |

### 3.5 Short & Punchy

#### Aqo
| Attribute | Detail |
|---|---|
| **CLI form** | `aqo init`, `aqo dev` |
| **Tagline** | "Aqo — agent queue orchestration" |
| **Pros** | Ultra-short (3 chars); preserves initials of current name; unique |
| **Cons** | No inherent meaning; pronunciation unclear (ah-ko? ay-kyo?); hard to search |
| **Availability** | ✅ Likely available — uncommon string |

#### Torq
| Attribute | Detail |
|---|---|
| **CLI form** | `torq init`, `torq dev` |
| **Tagline** | "Apply force to your workflows" |
| **Pros** | 4 chars; powerful imagery (torque = rotational force); memorable |
| **Cons** | Torq.io exists (security automation); spelling may confuse |
| **Availability** | ⚠️ Torq is an active security automation company |

#### Flux
| Attribute | Detail |
|---|---|
| **CLI form** | `flux init`, `flux dev` |
| **Tagline** | "Keep your agents in flux" |
| **Pros** | 4 chars; evokes continuous flow and change; strong brand potential |
| **Cons** | ⛔ Extremely overloaded — FluxCD (GitOps), Facebook Flux architecture, many others |
| **Availability** | ❌ Major conflicts across multiple ecosystems |

#### Relay
| Attribute | Detail |
|---|---|
| **CLI form** | `relay init`, `relay dev` |
| **Tagline** | "Relay work to your agents" |
| **Pros** | Perfect metaphor (passing work along); works as verb; 2 syllables; 5 chars |
| **Cons** | Facebook's Relay (GraphQL); relay as a concept is common |
| **Availability** | ⚠️ Likely conflicts — Relay is a well-known GraphQL framework |

#### Convoy
| Attribute | Detail |
|---|---|
| **CLI form** | `convoy init`, `convoy dev` |
| **Tagline** | "Move work in convoy" |
| **Pros** | Implies coordinated movement of many units; 2 syllables; strong visual identity (trucks/ships) |
| **Cons** | Convoy (the trucking startup) went bankrupt but name is still recognized; 6 chars |
| **Availability** | ⚠️ Convoy exists as a webhooks gateway on GitHub; trucking company association |

#### Rally
| Attribute | Detail |
|---|---|
| **CLI form** | `rally init`, `rally dev` |
| **Tagline** | "Rally your agents" |
| **Pros** | Energetic; implies bringing resources together; works as verb; 5 chars |
| **Cons** | Rally Software (CA Agile Central) was a major project management tool |
| **Availability** | ⚠️ Rally has existing associations in project management |

### 3.6 Mythological & Abstract

#### Hermes
| Attribute | Detail |
|---|---|
| **CLI form** | `hermes init`, `hermes dev` |
| **Tagline** | "Swift messenger for your agents" |
| **Pros** | Rich mythology (messenger of the gods); implies speed and delivery; 2 syllables |
| **Cons** | Facebook's Hermes JS engine; Hermès luxury brand; very commonly used name |
| **Availability** | ⚠️ Multiple conflicts — Meta's Hermes, various other projects |

#### Conduit
| Attribute | Detail |
|---|---|
| **CLI form** | `conduit init`, `conduit dev` |
| **Tagline** | "The conduit for agent workflows" |
| **Pros** | Perfect metaphor (channel for flow); professional; 2 syllables; 7 chars |
| **Cons** | Conduit (data streaming platform by Meroxa) exists; several other uses |
| **Availability** | ⚠️ Conduit is an active open-source data streaming tool |

#### Nexus
| Attribute | Detail |
|---|---|
| **CLI form** | `nexus init`, `nexus dev` |
| **Tagline** | "The nexus of agent orchestration" |
| **Pros** | Means "connection point"; powerful; 2 syllables; 5 chars |
| **Cons** | Sonatype Nexus (artifact repository) is very well-known; overused in tech |
| **Availability** | ❌ Major conflict — Sonatype Nexus is ubiquitous in Java/DevOps |

---

## 4. Top 3 Recommendations

### 🥇 Best Overall Name: **Relay**

Despite the Facebook/Meta GraphQL framework sharing the name, **Relay** is the strongest all-around candidate:

- **Metaphor strength**: A relay is the act of passing work from one runner to the next — *exactly* what an agent queue orchestrator does. The relay race metaphor is universally understood.
- **Verb form**: "Relay that task," "Relay it to the workers" — natural and grammatically correct.
- **CLI ergonomics**: `relay init`, `relay dev`, `relay status` — 5 characters, easy to type, impossible to misspell.
- **Differentiation**: The Meta GraphQL Relay is a frontend framework in a completely different domain. In the agent/orchestration space, "Relay" is distinctive.
- **Brand potential**: Strong logo options (baton pass, relay tower, signal relay); works as hashtag (#relay); community identity ("Relayers").
- **Package strategy**: Use `flint-ai` or `flint-orchestrator` on registries where `flint` is taken; claim `@flint` scope on npm if possible.

> **Tagline**: *"Relay — pass work to your agents, reliably."*

---

### 🥈 Best CLI Experience: **Aqo**

For pure command-line ergonomics, nothing beats **Aqo**:

- **Typing speed**: 3 characters — `aqo init` is as fast as `git init`. In a world where developers type commands hundreds of times per day, every character counts.
- **Continuity**: Preserves the initials of "Agent Queue Orchestrator," making migration feel natural for existing users.
- **Uniqueness**: "Aqo" is virtually unused anywhere. Google returns near-zero results. Package registries are almost certainly clear.
- **Pronunciation**: Standardize on "AH-ko" (like "echo" with an A) — short, pleasant, international-friendly.
- **Tradeoffs**: The name carries no inherent meaning, which means the brand must be *built* rather than *inherited*. This requires more marketing effort but creates a stronger long-term brand (think: "Git" meant nothing before Linus chose it).

> **Tagline**: *"Aqo — agent orchestration, accelerated."*

---

### 🥉 Best Brand Potential: **Convoy**

For long-term brand building and community identity, **Convoy** has the richest potential:

- **Visual storytelling**: A convoy is a group of vehicles moving together in coordination — a perfect metaphor for agents processing queued work. The imagery is vivid and universal.
- **Logo potential**: Truck fleet, ship convoy, data packets moving in formation — multiple strong visual directions.
- **Community identity**: "Convoy users," "Join the Convoy," "Convoy contributors" all sound natural and energetic.
- **Emotional resonance**: Convoys imply strength in numbers, protection, coordinated movement — exactly the reliability story an orchestrator wants to tell.
- **CLI comfort**: `convoy init`, `convoy deploy`, `convoy status` — 6 characters, satisfying to type.
- **Tradeoffs**: The defunct trucking startup Convoy may cause initial confusion, but that association will fade. The `convoy` webhooks project on GitHub is low-profile.

> **Tagline**: *"Convoy — move work together."*

---

### Recommendation Summary

| Criterion | Relay | Aqo | Convoy |
|---|---|---|---|
| Memorability | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| CLI ergonomics | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Uniqueness | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Meaning / evocation | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| Brand / community | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Availability risk | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Overall** | **🥇 Recommended** | **🥈 Runner-up** | **🥉 Strong alternative** |

**Final recommendation**: The project ultimately chose **Flint** as the new name.

---

## 5. Migration Plan

The rebrand proceeded with "Flint" as the chosen name:

### Phase 1: Preparation (Weeks 1–2)

| Task | Details |
|---|---|
| Secure package names | Register `flint` (or scoped `@flint-ai`) on PyPI, npm, NuGet, Docker Hub |
| Secure domains | Acquire `flint.dev`, `getflint.dev`, or `flint-ai.dev` |
| Secure social handles | Twitter/X, GitHub org, Discord server |
| Design brand assets | Logo, color palette, CLI banner, favicon |
| Create redirect plan | Map all old URLs → new URLs |

### Phase 2: Code & Package Migration (Weeks 3–4)

| Task | Details |
|---|---|
| GitHub repo rename | Rename `agent-queue-orchestrator` → `flint` (GitHub auto-redirects old URL) |
| Or: new repo | Create `flint` repo, archive old one with pointer to new location |
| Update all internal references | Package names, imports, CLI binary name, docs |
| Publish under new name | Publish to all registries under the new name |
| Legacy package | Publish a final version of old package that depends on new package + prints deprecation notice |

### Phase 3: Redirect & Communication (Weeks 5–6)

| Task | Details |
|---|---|
| Documentation | Update all docs, README, website to new name |
| Blog post | "Introducing Flint: Agent Queue Orchestrator gets a new name" |
| Registry deprecation | Mark old packages as deprecated with pointer to new name |
| URL redirects | Set up 301 redirects: old domain → new domain, old docs → new docs |
| Community notification | Announce in Discord, GitHub Discussions, Twitter, mailing list |

### Phase 4: Sunset (Weeks 7–12)

| Task | Details |
|---|---|
| Monitor old package downloads | Track how quickly users migrate |
| Support both names | Accept both `agent-queue-orchestrator` and `flint` in CLI for 2 major versions |
| Alias support | `alias aqo=flint` in installation scripts for transitional comfort |
| Remove old references | After 2 major versions, remove backward compatibility |

### Timeline Overview

```
Week 1-2:  ████████░░░░░░░░░░░░░░░░  Preparation
Week 3-4:  ░░░░░░░░████████░░░░░░░░  Code & Packages
Week 5-6:  ░░░░░░░░░░░░░░░░████████  Communication
Week 7-12: ░░░░░░░░░░░░░░░░░░░░████  Sunset old name
```

### Risk Mitigation

| Risk | Mitigation |
|---|---|
| Users can't find the project | 301 redirects + deprecated old packages pointing to new name |
| Broken CI/CD pipelines | Support old CLI name as alias for 6+ months |
| SEO loss | Redirect strategy preserves link equity; blog post generates new signals |
| Community confusion | Clear, repeated communication across all channels |
| Package name squatting | Secure names ASAP, before any public announcement |

---

*Document prepared for community discussion. All recommendations are based on public information and general availability assumptions — formal trademark and registry searches should be conducted before any final decision.*
