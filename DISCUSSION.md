# Discussion Questions

Answer the **Shared Questions** section plus the **one track section** specified in your email (Solutions Architect OR Data Engineer). 

Aim for 2-4 sentences per answer unless otherwise noted. We value clarity and depth over length.

---

## Shared Questions (everyone answers)

### 1. Troubleshooting

If you could not complete the assessment or got stuck at any point, what went wrong and what did you try to troubleshoot?

**Your answer:**
The assessment was completed. The IAM user couldn’t call Bedrock directly so make test-haiku can’t run from my lab machine. That’s okay, it worked through the deployed pipeline, which was really what I think you wanted. 
First terraform apply failed, but that also was expected based on the read me. 

Note: I took a very cautions approach and put effort into a testing plan for the parsing and such up front. I also did this over multiple sitting as I was weaving this between other activiites of my own. So the exercise itself went super fast.

### 2. Proof of Completion

Paste the S3 URI to one of your result files (e.g., `s3://nmd-genai-<your-name>-documents/results/<document-id>.json`).

**Your answer:**
s3://nmd-genai-trent-rossiter-documents/results/financial-filing.json

### 3. Prompt Engineering

How would you improve the classification prompt to handle ambiguous documents that could match multiple types? What techniques would you use to ensure consistent JSON output from the LLM?

**Your answer:**
The JSON output IMO is the riskiest piece. I had conversation with Claude before the clock started because i was seeing issues in the way Claude interpreted the mappings. I ended up overriding those mappings with my own interpretations and  creating a test mechanism ahead of time so that I wouldn’t be validating outputs manually after the clock started.

Regrading long term consistency - testing is everything. I made assumptions on data structure using a very small sample of data. If this were real I would want a lot more data and assumptions validated.

### 4. Error Handling

How would you handle Bedrock throttling (429 errors) in a production pipeline? What retry strategy would you implement, and how would it interact with Step Functions' built-in error handling?

**Your answer:**
Isolate the throttling errors then implement a retries with exponential backoff, or some variation of it, so that each wait between retries is double the previous.  You could also implement something called Jitter - this adds randomness to the wait so that if a large number of documents get loaded at the same time they don’t all try to retry at the same time too triggering throttling issues again. Include a max attempts as well as a precaution.

### 5. Enterprise Readiness

Assume a CTO prototyped this pipeline over a weekend using AI code assistants. It works for demos but needs to go to production for a Fortune 500 client.

Write a prioritized list of changes organized by:
1. **Must-fix before production** — what would block a launch?
2. **Should-fix in the first sprint** — what's important but not blocking?
3. **Nice-to-have for long-term maintainability** — what would you plan for later?

Consider security, error handling, observability, testing, CI/CD, and infrastructure hardening.

**Your answer:**
Must-fix before production - Start with Security, error handling, infrastructure hardening and testing. This would cover things like roles on the Lamba, scoping on the model (already done for the experiment, permission on the S3 bucket, etc. Refine error handling, we talked about throttling errors but if the input document isn’t valid you want to fail fast and move on. Obviously you’ll want more than 4 test documents :-)

Should-fix in the first sprint - Then observability - logging, dashboard with performance metrics and error counts. 

Nice-to-have for long-term maintainability - CI/CD - I’ve worked with clients that wanted full CI/CD before we finished a POC or MVP. I wouldn’t invest in CI/CD before you even know if this solutions will create the business outcome.

### 4. Terraform — Adding a Pipeline Step

A new "validate" Lambda needs to be added to the pipeline between Extract and Aggregate. It will validate the extracted fields against a schema before writing results. List every file you'd need to change and what you'd add to each.

**Your answer:**
I’m, admittedly,  not a terraform expert. It looks like the following:

main.tf

extract_lambda_arn    = module.lambda.extract_arn

<add validate here>

aggregate_lambda_arn  = module.lambda.aggregate_arn

state_machine.asl.json

Add a new state - it’s sequenced in the file.

When I put this into Claude, it gave me a full list that I could have put in here. If I were to do this for a client I’d lean really heavily on Claude for this task; this is exactly the sort of thing that Claude is super good at.
---

## Solutions Architect Track

*Answer this section only if your email specified Solutions Architect.*

### SA-1. Model Selection & Cost Architecture

This assessment restricts you to Claude Haiku. In a production system processing thousands of documents daily, how would you decide which model to use for classification vs. extraction? What factors (cost, latency, accuracy, token limits) would drive that decision? How would you implement cost attribution per client?

**Your answer:**
Classification - there are a slew of models specifically designed for classification now, Jev is one of the most talked about ones. It’s very fast and cheap. However, if the examples in this assessment represented the production data, I wouldn’t use an AI model at all, I would implement the classification in python. Python would be fast, cheap, accurate and wouldn’t use tokens. It relies heavily on the data being consistent though; maybe try it with a JEV backup.

Extraction: The extraction was a little trickier. While it is a JSON, the content part was messier (placements of colons, dashes new lines, etc.) I’d stick with AI for that.

How would you implement cost attribution per client? - Maybe a separate Bedrock app interface per client along with a tag that tracks costs back to the client. I’ve not done this before but my guess is that it’ll be straight forward.

### SA-2. Security Review

A client wants to process PHI (protected health information) through this pipeline. What changes are needed to meet HIPAA requirements? Think about data at rest, data in transit, Bedrock's data handling policies, IAM scoping, and logging.

**Your answer:**
Host it on HIPPA compliant services in AWS. Encrypt at rest (S3). TLS encrypt for data in transit. Cloudwatch for logs. Lock down the IAM policies - that was mostly talked about in the security section but is more important here.

### SA-3. Multi-Tenancy

A client wants to offer this pipeline as a SaaS feature where each of their customers uploads documents. How would you isolate tenants? Consider S3 partitioning, IAM scoping, cost attribution, and noisy-neighbor protection.

**Your answer:**
Set up that client with their own account and with their own tenant. They would have their own S3 buckets, IAM policies, billing isolated for that account and they wouldn’t have neighbors. If they need cost allocation for their customers we could set up that tagging concept discussed earlier for them.

### SA-4. Production Readiness Briefing

List the key points you'd convey to a client's VP of Engineering who approved this project but hasn't seen the implementation. What changes are needed before going to production, and how would you prioritize them?

**Your answer:**
This is very similar to the question about a prototype being created and now you want to roll it out to a fortune 500 company. 

---

## Data Engineer Track

*Answer this section only if your email specified Data Engineer.*

### DE-1. Data Quality & Validation

The pipeline trusts the LLM's JSON output without validation. How would you validate extracted fields against a schema? How would you handle extraction failures — retry, dead-letter queue, or flag for human review? What's your strategy?

**Your answer:**

### DE-2. Pipeline at Scale

This processes one document per Step Functions execution. Design a batch pipeline that handles 100,000 documents per day. What changes to the Step Functions architecture? Where would you parallelize, and where are the bottlenecks?

**Your answer:**

### DE-3. Observability & Data Lineage

How would you monitor this pipeline in production? What metrics, alerts, and dashboards would you build? A downstream team also needs to know which model version and prompt version produced each extraction. How would you track that lineage?

**Your answer:**

### DE-4. Caching & Deduplication

If the same document is uploaded twice, the pipeline currently processes it again at full cost. How would you implement caching or deduplication? Consider where in the pipeline to check, what to use as a cache key, and the tradeoffs of different storage options (DynamoDB, S3 metadata, Elasticache).

**Your answer:**
