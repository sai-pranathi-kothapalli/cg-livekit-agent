# Agent Worker

This folder contains the LiveKit agent worker code for the interview system.

## Structure

```
agent/
├── agent.py                 # Main agent entry point
├── run_console_agent.py     # Console mode agent runner
├── agents/                  # Agent implementation
│   ├── entrypoint.py        # LiveKit agent entrypoint
│   ├── professional_arjun.py  # Interview agent implementation
│   └── utils.py            # Agent utilities
└── requirements.txt         # Python dependencies

```

## Setup

1. Install dependencies:
```bash
cd agent
pip install -r requirements.txt
```

2. Ensure `.env.local` is in the project root (parent directory)

## Running the Agent

### Production Mode (Worker)
```bash
cd agent
python agent.py start
```

### Development Mode
```bash
cd agent
python agent.py dev
```

### Console Mode (for testing)
```bash
cd agent
python run_console_agent.py
```

## Dependencies

The agent imports from the `backend` folder for:
- `app.config` - Configuration
- `app.services` - Backend services
- `app.utils` - Utility functions

The agent automatically adds the `backend` directory to the Python path, so ensure the backend folder is at the same level as the agent folder.

## Notes

- The agent worker runs independently from the backend API server
- Both can run simultaneously (backend API + agent worker)
- The Procfile in the backend folder references this agent folder for deployment

