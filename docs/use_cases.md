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
- Data needed: mock employee record (name, job title, salary, start date) + `employment_verification_letter` template
- Success criteria: agent looks up the authenticated employee's real record, fills the template accurately, and produces a correctly formatted letter — never fabricates details, never generates a letter for someone else's data

## 4. Mileage claims for work travel
- Example query: "What's the mileage rate for using my own car for work trips?"
- Data needed: HMRC AMAP mileage rate docs
- Success criteria: correct current official rate, states the rate is HMRC-published (traceable to source)

## 5. Workplace pension (auto-enrolment) questions
- Example query: "How do I opt out of the pension scheme?"
- Data needed: NEST pension public guidance
- Success criteria: accurate process explanation, correctly distinguishes "information" from "action" (agent explains, doesn't opt someone out itself)

## 6. Booking leave
- Example query: "I need to book a week off for my holiday starting next month."
- Data needed: mock leave balance DB (to check availability) + ticketing tool (to submit the request)
- Success criteria: agent checks remaining balance covers the request, submits a ticket with start date/end date/reason, and correctly sets it to "pending line manager approval" — never auto-approves itself (guardrail-triggering case)

## 7. Grievance / who do I raise a complaint with
- Example query: "I have a complaint about a colleague, who do I speak to?"
- Data needed: ACAS grievance procedure docs
- Success criteria: correct escalation contact/process; always escalates to a human rather than attempting to resolve the complaint itself (guardrail-triggering case)

## 8. P45 / P60 request
- Example query: "Can I get a copy of my P60 for this tax year?"
- Data needed: mock employee record (name, employee ID, hire date) + `p45_p60_request` template
- Success criteria: agent correctly distinguishes P45 (leaver) vs P60 (annual) intent, fills only the fields it actually holds (never fabricates a tax reference number it doesn't have), and routes the request for human approval rather than issuing the document itself (guardrail-triggering case)

## 9. Change of personal details
- Example query: "I need to update my bank details for payroll."
- Data needed: mock employee record (current values) + `change_of_personal_details_form` template
- Success criteria: agent records the requested change accurately and always routes it to "pending HR review" — never applies a personal-data change itself, especially for bank details (guardrail-triggering case)

## 10. Flexible working request
- Example query: "How do I request to change my working hours, and can you help me submit it?"
- Data needed: ACAS flexible working guidance (process/eligibility) + mock employee record (current role/pattern) + `flexible_working_request_form` template
- Success criteria: agent explains the real ACAS-grounded process correctly, fills the form with the employee's actual current details, and submits it as "pending manager review" — combines RAG grounding with template-filling in one flow