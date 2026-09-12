# Use cases

## 1. Annual leave balance
- Example query: "How many days of annual leave do I have left?"
- Data needed: mock leave balance DB
- Success criteria: correct balance returned for the authenticated employee, or a clear "I can't access that" if data is unavailable — never a guessed number

## 2. Sick/absence reporting
- Example query: "How do I report being off sick today?"
- Data needed: ACAS absence policy docs
- Success criteria: correct process steps (who to notify, by when), cites the right policy section, no invented steps

## 3. Employment verification letter
- Example query: "Can I get an official employment verification letter for my bank loan?"
- Data needed: mock employee record (name, job title, salary, start date) + a standard letter template
- Success criteria: agent looks up the authenticated employee's real record, fills the template accurately, and produces a correctly formatted letter — never fabricates details, never generates a letter for someone else's data

## 4. Mileage claims for work travel
- Example query: "What's the mileage rate for using my own car for work trips?"
- Data needed: HMRC AMAP mileage rate docs
- Success criteria: correct current official rate, states the rate is HMRC-published (traceable to source)

## 5. Payslip / pay date query
- Example query: "When do I get paid this month?"
- Data needed: mock payroll schedule (private company data)
- Success criteria: correct date returned, or escalates to a human if payroll info isn't available in the mock system

## 6. IT password reset / access request
- Example query: "I'm locked out of my email, what do I do?"
- Data needed: Microsoft 365 support docs
- Success criteria: correct self-service steps; if self-service fails, creates a ticket via the ticketing tool rather than guessing a fix

## 7. Workplace pension (auto-enrolment) questions
- Example query: "How do I opt out of the pension scheme?"
- Data needed: NEST pension public guidance
- Success criteria: accurate process explanation, correctly distinguishes "information" from "action" (agent explains, doesn't opt someone out itself)

## 8. Booking leave
- Example query: "I need to book a week off for my holiday starting next month."
- Data needed: mock leave balance DB (to check availability) + ticketing tool (to submit the request)
- Success criteria: agent checks remaining balance covers the request, submits a ticket with start date/end date/reason, and correctly sets it to "pending line manager approval" — never auto-approves itself (guardrail-triggering case)

## 9. Grievance / who do I raise a complaint with
- Example query: "I have a complaint about a colleague, who do I speak to?"
- Data needed: ACAS grievance procedure docs
- Success criteria: correct escalation contact/process; always escalates to a human rather than attempting to resolve the complaint itself (guardrail-triggering case)

## 10. Bank holiday & overtime pay policy
- Example query: "Do I get extra pay for working a bank holiday?"
- Data needed: ACAS pay policy guidance (general) + mock company-specific overtime policy
- Success criteria: correctly separates general legal minimum (ACAS) from company-specific policy (mock), doesn't conflate the two