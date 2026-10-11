# AI Agent for Maintenance Ticket Prioritization

This project implements a lightweight maintenance-ticket triage system for renewable-energy operations. It classifies incoming issues, estimates severity, recommends a root cause, suggests the next action, and routes the ticket to the correct operations team.

## What the app does

- Reads ticket text from the user-facing form or API request
- Uses a lightweight keyword + similarity classifier over the bundled dataset
- Assigns a severity score and priority label
- Suggests a probable root cause and operational action
- Routes the ticket to the likely maintenance team
- Exposes the workflow through a Python HTTP API and HTML frontend

## Project structure

- backend/app.py — Python HTTP server and rule-based triage logic
- frontend/index.html — simple interactive demo UI
- data/maintenance_tickets.csv — bundled sample dataset
- Procfile — Railway deployment entry point

## Model logic

The solution intentionally avoids heavy ML dependencies and instead uses a transparent, dependency-light NLP approach:

- Tokenize the ticket description and asset type
- Match the text against known category keywords from the sample dataset
- Score each category based on overlap and learned category patterns from the bundled CSV
- Apply operational heuristics for severity and routing defaults

This makes the app explainable, portable, and easy to run without external APIs or large model downloads.

## Evaluation approach

Because the bundled dataset is intentionally small, the evaluation focuses on a practical prototype check rather than a large statistical benchmark. The app uses the sample data as the reference set and reports the number of included categories and the decision confidence returned for each input.

## How to run locally

1. Open a terminal in the project root.
2. Start the app:

   python backend/app.py

3. Open the app in a browser:

   http://localhost:8000/

4. Test the API with an example payload using a POST request to:

   http://localhost:8000/api/run

   Example JSON:

   {
     "asset_type": "solar",
     "text": "Inverter 4 tripping repeatedly after noon, high temperature alarm visible."
   }

## Deployment note

The app is configured for Railway with the included Procfile:

web: python backend/app.py

To deploy on Railway:
1. Connect the repository to Railway.
2. Use the project folder as the app root.
3. Deploy using the Procfile above.
4. Verify the public Railway URL responds correctly.

## Assumptions and limitations

- The dataset is intentionally small and uses synthetic examples rather than full production incident history.
- The model is a prototype and is designed to be transparent and explainable rather than highly generalized.
- Severity and routing rules are tuned for the sample operation patterns in the bundled dataset.
- Real production usage would need more data, alerting integration, and a human approval workflow.

## Production-readiness gaps

- No persistent database or logging backend yet
- No authentication or role-based access
- No advanced retrieval or LLM integration
- No automatic retraining pipeline

These are acceptable for this demo task, but they are the next important items for real-world operational use.
