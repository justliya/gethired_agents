#!/usr/bin/env python
"""
Entry point for the Speaker Agent.
Initializes and starts the agent's server with improved error handling and health checks.
"""

# CRITICAL: This MUST be at the very top before any imports
import os
import sys
import json
from pathlib import Path
import logging
import argparse
import uvicorn
import asyncio
import signal
import time
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from typing import Set, Optional

# Load environment variables with fallback paths
env_paths = [
    os.path.join(os.path.dirname(__file__), '..', '..', '.env'),
    os.path.join(os.path.dirname(__file__), '.env'),
    '/app/.env'
]

for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=True)
        break

from .task_manager import TaskManager
from .agent import root_agent
from common.a2a_server import create_agent_server

# Constants
DEFAULT_TIMEOUT = 60.0
HEALTH_CHECK_INTERVAL = 30.0
STARTUP_TIMEOUT = 120.0

class HealthChecker:
    """Health check manager for the speaker agent"""
    
    def __init__(self):
        self.start_time = time.time()
        self.last_health_check = time.time()
        self.is_healthy = False
        self.health_status = {
            'status': 'starting',
            'uptime': 0,
            'last_check': None,
            'errors': []
        }
    
    def update_health(self, status: str, error: Optional[str] = None):
        """Update health status"""
        self.last_health_check = time.time()
        self.health_status.update({
            'status': status,
            'uptime': self.last_health_check - self.start_time,
            'last_check': self.last_health_check,
        })
        
        if error:
            self.health_status['errors'].append({
                'timestamp': self.last_health_check,
                'error': error
            })
            # Keep only last 10 errors
            self.health_status['errors'] = self.health_status['errors'][-10:]
        
        self.is_healthy = status == 'healthy'
    
    def get_health(self) -> dict:
        """Get current health status"""
        return {
            **self.health_status,
            'uptime': time.time() - self.start_time
        }

# Global health checker
health_checker = HealthChecker()

# Logging configuration
def setup_logging(log_level: str = "info"):
    """Setup logging with proper formatting"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Clear existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Setup new handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format))
    
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

def validate_environment():
    """Validate required environment variables and configurations"""
    logger = logging.getLogger(__name__)
    
    # Check Firebase configuration
    firebase_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
    google_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    
    issues = []
    
    if not firebase_bucket:
        issues.append("FIREBASE_STORAGE_BUCKET not set")
    
    if not project_id:
        issues.append("GOOGLE_CLOUD_PROJECT not set")
    
    if google_creds and not os.path.exists(google_creds):
        issues.append(f"Google credentials file not found: {google_creds}")
    elif google_creds:
        try:
            with open(google_creds, 'r') as f:
                creds = json.load(f)
                if 'project_id' not in creds:
                    issues.append("Google credentials file missing project_id")
        except json.JSONDecodeError:
            issues.append("Google credentials file is not valid JSON")
        except Exception as e:
            issues.append(f"Error reading credentials file: {e}")
    
    # Check MCP configuration
    mcp_port = os.getenv('MCP_HTTP_PORT', '3000')
    try:
        int(mcp_port)
    except ValueError:
        issues.append(f"Invalid MCP_HTTP_PORT: {mcp_port}")
    
    if issues:
        logger.warning("Environment validation issues found:")
        for issue in issues:
            logger.warning(f"  - {issue}")
        health_checker.update_health('degraded', f"Environment issues: {', '.join(issues)}")
    else:
        logger.info("Environment validation passed")
    
    return len(issues) == 0

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
        default=os.getenv("LOG_LEVEL", "info").lower(),
        help="Set the logging level"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("SPEAKER_AGENT_TIMEOUT", DEFAULT_TIMEOUT)),
        help="Timeout for agent operations in seconds"
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=int(os.getenv("HEALTH_PORT", "8080")),
        help="Port for health check endpoint"
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=STARTUP_TIMEOUT,
        help="Maximum time to wait for startup"
    )
    return parser.parse_args()

async def wait_for_dependencies():
    """Wait for external dependencies to be ready"""
    logger = logging.getLogger(__name__)
    
    # Check MCP service
    mcp_port = os.getenv('MCP_HTTP_PORT', '3000')
    mcp_url = f"http://localhost:{mcp_port}"
    
    logger.info(f"Checking MCP service at {mcp_url}")
    
    import aiohttp
    async with aiohttp.ClientSession() as session:
        for attempt in range(30):  # 30 attempts with 2 second intervals = 60 seconds max
            try:
                async with session.get(f"{mcp_url}/health", timeout=5) as response:
                    if response.status == 200:
                        logger.info("MCP service is ready")
                        return True
            except Exception as e:
                logger.debug(f"MCP service check attempt {attempt + 1}: {e}")
            
            await asyncio.sleep(2)
    
    logger.warning("MCP service not ready after 60 seconds, continuing anyway")
    return False

async def create_health_server(port: int):
    """Create a simple health check server"""
    from aiohttp import web
    
    async def health_handler(request):
        health_data = health_checker.get_health()
        status_code = 200 if health_checker.is_healthy else 503
        return web.json_response(health_data, status=status_code)
    
    async def ready_handler(request):
        # Simple readiness check
        if health_checker.is_healthy:
            return web.json_response({'status': 'ready'})
        else:
            return web.json_response({'status': 'not ready'}, status=503)
    
    app = web.Application()
    app.router.add_get('/health', health_handler)
    app.router.add_get('/ready', ready_handler)
    app.router.add_get('/', health_handler)  # Default route
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    return runner

class TaskTracker:
    """Track and manage async tasks"""
    
    def __init__(self):
        self.running_tasks: Set[asyncio.Task] = set()
        self.logger = logging.getLogger(f"{__name__}.TaskTracker")
    
    def add_task(self, task: asyncio.Task, name: str = None):
        """Add a task to tracking"""
        self.running_tasks.add(task)
        task.add_done_callback(self._task_done_callback)
        if name:
            task.set_name(name)
        self.logger.debug(f"Added task: {name or task.get_name()}")
    
    def _task_done_callback(self, task: asyncio.Task):
        """Callback when task is done"""
        self.running_tasks.discard(task)
        if task.cancelled():
            self.logger.debug(f"Task cancelled: {task.get_name()}")
        elif task.exception():
            self.logger.error(f"Task failed: {task.get_name()}: {task.exception()}")
    
    async def cleanup(self):
        """Clean up all running tasks"""
        if not self.running_tasks:
            return
        
        self.logger.info(f"Cleaning up {len(self.running_tasks)} running tasks...")
        
        # Cancel all tasks
        for task in self.running_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for them to finish
        await asyncio.gather(*self.running_tasks, return_exceptions=True)
        self.running_tasks.clear()

async def main():
    args = parse_args()
    
    # Setup logging first
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    logger.info("=== Speaker Agent Starting ===")
    logger.info(f"Host: {args.host}:{args.port}")
    logger.info(f"Health check port: {args.health_port}")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info(f"Log level: {args.log_level}")
    
    # Update health status
    health_checker.update_health('starting')
    
    # Validate environment
    env_valid = validate_environment()
    if not env_valid:
        logger.warning("Environment validation failed, but continuing...")
    
    # Initialize task tracker
    task_tracker = TaskTracker()
    
    # Signal handler for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        shutdown_event.set()
    
    # Set up signal handlers
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        logger.warning("Signal handlers not supported on this platform")
    
    health_runner = None
    
    try:
        # Start health check server
        health_runner = await create_health_server(args.health_port)
        logger.info(f"Health check server started on port {args.health_port}")
        
        # Wait for dependencies
        await wait_for_dependencies()
        
        # Initialize agent with timeout
        logger.info("Initializing agent...")
        health_checker.update_health('initializing')
        
        startup_task = asyncio.create_task(root_agent)
        task_tracker.add_task(startup_task, "agent_init")
        
        try:
            agent_instance, exit_stack = await asyncio.wait_for(
                startup_task, 
                timeout=args.startup_timeout
            )
            logger.info(f"Agent instance created: {agent_instance.name}")
        except asyncio.TimeoutError:
            health_checker.update_health('failed', 'Agent initialization timeout')
            raise RuntimeError(f"Agent initialization timed out after {args.startup_timeout}s")

        async with exit_stack:
            # Initialize TaskManager
            try:
                tm = TaskManager(agent=agent_instance, timeout=args.timeout)
            except TypeError:
                tm = TaskManager(agent=agent_instance)
                if hasattr(tm, 'timeout'):
                    tm.timeout = args.timeout
            
            # Determine final port (Cloud Run uses PORT env var)
            final_port = int(os.getenv('PORT', args.port))
            logger.info(f"Using port: {final_port} (from {'PORT env var' if 'PORT' in os.environ else 'args'})")

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

            # Add health status to app
            @app.get("/health")
            async def app_health():
                return health_checker.get_health()

            logger.info(f"Speaker Agent A2A server starting on {args.host}:{final_port}")
            health_checker.update_health('starting_server')
            
            config = uvicorn.Config(
                app, 
                host=args.host, 
                port=final_port, 
                log_level=args.log_level,
                access_log=args.log_level == "debug"
            )
            server = uvicorn.Server(config)
            
            # Start server as a task
            server_task = asyncio.create_task(server.serve())
            task_tracker.add_task(server_task, "uvicorn_server")
            
            # Mark as healthy
            health_checker.update_health('healthy')
            logger.info("Speaker Agent is ready and healthy")
            
            # Wait for shutdown signal or server completion
            done, pending = await asyncio.wait(
                [server_task, asyncio.create_task(shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                
            if shutdown_event.is_set():
                logger.info("Graceful shutdown initiated")
                health_checker.update_health('shutting_down')
                server.should_exit = True
                await server_task
                
    except asyncio.CancelledError:
        logger.info("Main task was cancelled")
        health_checker.update_health('cancelled')
    except Exception as e:
        logger.error(f"Error during server execution: {e}", exc_info=True)
        health_checker.update_health('failed', str(e))
        raise
    finally:
        # Clean up
        logger.info("Cleaning up resources...")
        
        # Clean up tasks
        await task_tracker.cleanup()
        
        # Clean up health server
        if health_runner:
            await health_runner.cleanup()
        
        logger.info("Speaker Agent shutdown complete")

if __name__ == "__main__":
    try:
        # Windows compatibility
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Speaker Agent stopped by user.")
        sys.exit(0)
    except Exception as e:
        logging.getLogger(__name__).error(f"Error during server startup: {e}", exc_info=True)
        sys.exit(1)