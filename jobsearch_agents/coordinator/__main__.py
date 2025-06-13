#!/usr/bin/env python
"""
Entry point for the Speaker Agent.
Initializes and starts the agent's server.
"""

# CRITICAL: This MUST be at the very top before any imports
import os
import sys

# Set timeout environment variable before any imports
os.environ['MCP_CLIENT_TIMEOUT'] = '60.0'

# Monkey patch the MCP session timeout
try:
    from datetime import timedelta as original_timedelta
    class PatchedTimedelta(original_timedelta):
        def __new__(cls, seconds=60, **kwargs):
            if seconds == 5:
                seconds = float(os.getenv('MCP_CLIENT_TIMEOUT', '60.0'))
            return super().__new__(cls, seconds=seconds, **kwargs)
    sys.modules['datetime'].timedelta = PatchedTimedelta
except Exception as e:
    print(f"Warning: Could not patch MCP timeout: {e}", file=sys.stderr)

import logging
import argparse
import uvicorn
import asyncio
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

from .task_manager import TaskManager
from .agent import root_agent
from common.a2a_server import create_agent_server

# Constants
default_timeout = 60.0

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description="Start the Speaker Agent server")
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("SPEAKER_HOST", "0.0.0.0"),
        help="Host to bind the server to"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SPEAKER_PORT", "8003")),
        help="Port to bind the server to"
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default=os.getenv("LOG_LEVEL", "info"),
        help="Set the logging level"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("SPEAKER_AGENT_TIMEOUT", default_timeout)),
        help="Timeout for agent operations in seconds"
    )
    return parser.parse_args()

async def main():
    args = parse_args()

    # Apply log level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    logger.info("Starting Speaker Agent A2A Server initialization...")
    logger.info(f"Agent timeout set to: {args.timeout} seconds")

    # Instantiate agent and exit stack
    agent_instance, exit_stack = await root_agent
    logger.info(f"Agent instance created: {agent_instance.name}")

    async with exit_stack:
        # Initialize TaskManager
        try:
            tm = TaskManager(agent=agent_instance, timeout=args.timeout)
        except TypeError:
            tm = TaskManager(agent=agent_instance)
            if hasattr(tm, 'timeout'):
                tm.timeout = args.timeout
        
        # Determine bind address
        host = args.host
        port = int(os.getenv('PORT', args.port))

        # Create FastAPI app
        try:
            app = create_agent_server(
                name=agent_instance.name,
                description=agent_instance.description,
                task_manager=tm,
                timeout=args.timeout
            )
        except TypeError:
            app = create_agent_server(
                name=agent_instance.name,
                description=agent_instance.description,
                task_manager=tm
            )

        # Add CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        logger.info(f"Speaker Agent A2A server starting on {host}:{port}")
        config = uvicorn.Config(app, host=host, port=port, log_level=args.log_level)
        server = uvicorn.Server(config)
        await server.serve()

if __name__ == "__main__":
    try:
        if os.getenv("ASYNCIO_TIMEOUT"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Speaker Agent server stopped by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error during server startup: {e}", exc_info=True)
        sys.exit(1)