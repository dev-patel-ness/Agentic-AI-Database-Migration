Capstone Assessment Framework

1. Overall Rating Structure

This gives enough importance to the team outcome while ensuring that individual learning and contribution are independently assessed.

2. Team Project Evaluation – 60 Points

The team should be evaluated on the working solution, rather than only documentation or presentation.

A. Business Problem & Solution Design – 8 Points

The team should be able to explain:

What problem are we solving, why is AI/Agentic AI appropriate, and how does the proposed architecture solve it?

B. AI Engineering Implementation – 15 Points

This should be one of the most important sections because the programme is an AI Engineering programme.

Not every project needs every item to the same extent.

For example, the Database Migration Assistant should demonstrate agentic workflow, tools, validation and RAG, while the Knowledge Assistant may place greater emphasis on RAG and retrieval quality.

3. Cloud & Application Engineering – 10 Points

The objective is to ensure that the capstone is not simply:

"A Python script calling an LLM."

It should demonstrate the enterprise AI engineering practices covered during the programme.

4. Testing, Validation & Quality – 8 Points

For agentic applications, the team should demonstrate examples where the AI does not produce the expected answer and explain how the application handles the situation.

5. Observability, LLMOps & Security – 7 Points

This is particularly important because the course covers LLMOps, observability, governance and production readiness.

6. Documentation & Presentation – 7 Points

7. Individual Contribution – 30 Points

This is the most important part for a team-based capstone.

I would not simply ask:

"What did you contribute?"

Participants should provide evidence of contribution.

Individual Contribution Matrix

8. Individual Contribution Should Be Defined Before Development

At the beginning of the capstone, every team should prepare an Individual Responsibility Matrix.

For example, for a 3-member team:

9. Individual Viva / Technical Defense – 10 Points

This is particularly useful for identifying whether each participant genuinely understands their contribution.

Each participant gets approximately 10–15 minutes.

Suggested Questions

For example:

Architecture

Explain the part of the architecture you implemented.

AI

Why did you choose this LLM/agent approach?

RAG

How did you decide chunk size and retrieval strategy?

Agentic AI

What happens if Agent A produces an incorrect result?

Engineering

What happens when the downstream service fails?

Security

How are credentials and sensitive information protected?

Testing

How did you validate that your implementation works?

Production

What would you change if this system had 10,000 users?

Troubleshooting

Here is an error from your module. How would you investigate it?

This makes it difficult for someone to simply depend on another team member's implementation.

10. Capstone Completion Criteria

I would also establish a minimum completion gate.

A project should not be considered "Completed" merely because the team gives a successful demo.

Mandatory completion criteria

The team should demonstrate:

Business problem clearly defined

Architecture implemented

Core AI functionality working

Agent/RAG workflow working where applicable

Backend/API working

Data persistence implemented

Authentication/security where applicable

Error handling

Test cases

AI output evaluation

Logging/tracing

Deployment using Docker

Cloud deployment or deployment-ready implementation

Technical documentation

User/business documentation

Source code repository

Final demonstration

Individual contribution evidence

11. Suggested Rating Levels

Instead of only giving Points, I recommend giving a completion level as well.

I would use these levels descriptively, while keeping the actual score based on the 100-Point rubric above.


| Assessment Area | Weightage | Purpose |
|---|---|---|
| Team Project Evaluation | 60 Points | Quality and completeness of the overall capstone |
| Individual Contribution | 30 Points | Actual technical and functional contribution of each participant |
| Individual Viva / Technical Defense | 10 Points | Ability to explain, defend and troubleshoot their contribution |
| Total | 100 Points | Final individual capstone score |


| Criteria | Points |
|---|---|
| Problem clearly understood and defined | 2 |
| Appropriate AI/Agentic AI solution proposed | 2 |
| Architecture and component design | 2 |
| Clear end-to-end workflow | 2 |


| Criteria | Points |
|---|---|
| LLM integration | 2 |
| Prompt engineering | 2 |
| RAG / Knowledge Base where applicable | 3 |
| Agentic workflow / tool calling | 3 |
| LangChain / LangGraph implementation | 2 |
| Context/memory/state management | 1 |
| Guardrails / hallucination control | 2 |


| Criteria | Points |
|---|---|
| API/application implementation | 2 |
| AWS/service integration | 2 |
| Database/vector database integration | 2 |
| Docker/containerization | 1 |
| Kubernetes/cloud deployment | 1 |
| Configuration/secrets/environment management | 1 |
| Scalability/design considerations | 1 |


| Criteria | Points |
|---|---|
| Unit/API testing | 2 |
| AI output evaluation | 2 |
| End-to-end testing | 1 |
| Error/exception handling | 1 |
| Data/response validation | 1 |
| Edge-case testing | 1 |


| Criteria | Points |
|---|---|
| Logging and tracing | 1 |
| LangSmith/LangFuse or equivalent AI observability | 1 |
| Monitoring | 1 |
| Security/authentication/authorization | 1 |
| Prompt/model/version management | 1 |
| Cost/token/inference considerations | 1 |
| Responsible AI / governance | 1 |


| Criteria | Points |
|---|---|
| Architecture documentation | 2 |
| Setup/deployment documentation | 1 |
| API/technical documentation | 1 |
| User/business documentation | 1 |
| Final presentation/demo | 2 |


| Area | Points |
|---|---|
| Assigned module/functionality delivered | 10 |
| Code/technical implementation | 6 |
| AI/Agentic AI contribution | 5 |
| Testing/debugging/integration | 3 |
| Documentation | 2 |
| Collaboration & ownership | 2 |
| Code/demo evidence | 2 |
| Total | 30 |


| Participant | Primary Responsibility | Secondary Responsibility |
|---|---|---|
| Member 1 | RAG & Knowledge Base | Evaluation |
| Member 2 | Agentic Workflow / LangGraph | Prompt Engineering |
| Member 3 | FastAPI & Application Layer | Security |


| Level | Description |
|---|---|
| Level 1 – Incomplete | Core requirements are missing or system is largely non-functional |
| Level 2 – Basic Completion | Core functionality works but significant engineering gaps remain |
| Level 3 – Good Completion | Functional solution with appropriate AI engineering practices |
| Level 4 – Advanced Completion | Strong enterprise architecture, AI engineering, testing and deployment |
| Level 5 – Production-Oriented | Highly complete solution demonstrating production-readiness, observability, security and LLMOps |
