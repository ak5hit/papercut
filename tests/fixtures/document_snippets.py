"""Real document excerpts extracted from PDFs in the repo.

Used by contextualizer tests to verify the LLM can resolve implicit references
in follow-up questions against genuine document content.
"""

ZAMP_EXPECTATIONS = (
    "What we expect from you\n"
    "- A working, deployed solution\n"
    "- A README explaining what you built, why you scoped it the way you did, "
    "and how to set it up\n"
    "- A public GitHub repository with your code\n"
    "What we evaluate: problem framing — how did you interpret the problem; "
    "product thinking — did you think about who this is for; "
    "UX decisions — does the experience make sense."
)

CRED_PROJECTS = (
    "Built Datalens, a centralized Model Context Protocol (MCP) server "
    "that standardizes data retrieval from Mixpanel; adopted across the org "
    "as the core data fetcher for multiple autonomous agents.\n"
    "Developed an autonomous Inference-Guard GitHub Action utilizing agentic "
    "coding to monitor critical config changes; auto-generates PRs to "
    "synchronize downstream data layers, preventing silent schema drift.\n"
    "Architected a natural language Insights Engine within the UCMS platform; "
    "integrated LLM agents via MCP to allow non-technical users to query "
    "campaign performance metrics via chat."
)

F1_DATABASE = (
    "F1 is a distributed relational database system built at Google "
    "to support the AdWords business. F1 is a hybrid database that combines "
    "high availability, the scalability of NoSQL systems like Bigtable, "
    "and the consistency and usability of traditional SQL databases. "
    "F1 is built on Spanner, which provides synchronous cross-datacenter "
    "replication and strong consistency."
)
