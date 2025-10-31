#!/usr/bin/env python3
"""
Deployment MCP Server for BetterGovPH Open Data Visualization

This MCP server handles automated deployments to servers via SSH.
"""

import asyncio
import logging
import paramiko
import os
from typing import Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeploymentMCPServer:
    """Deployment MCP Server for handling server deployments"""

    def __init__(self):
        self.ssh_client = None
        self.connected = False

    async def connect_to_server(
        self,
        host: str = "10.27.79.7",
        username: str = "joebert",
        key_name: str = "klti",
        port: int = 22,
        working_dir: str = "/home/joebert/open-data-visualization",
        password: str = None,
        deployment_type: str = "script",
        docker_image: str = None,
        docker_compose_file: str = None,
        run_precheck: bool = True,
        launch_agents_dir: str = "/home/joebert/.config/systemd/user/",
    ) -> Dict[str, Any]:
        """Connect to server via SSH with configurable defaults"""
        try:
            # Run pre-check if enabled
            if run_precheck:
                logger.info("🔍 Running pre-check before connection...")
                precheck_result = await self._run_precheck(working_dir)
                if not precheck_result["success"]:
                    return {
                        "success": False,
                        "error": f"Pre-check failed: {precheck_result['error']}",
                        "step": "precheck",
                        "precheck_details": precheck_result,
                    }
                logger.info("✅ Pre-check passed, proceeding with connection...")

            logger.info(f"🔗 Connecting to {host} as {username}...")

            # Initialize SSH client
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Get key path
            key_path = os.path.expanduser(f"~/.ssh/{key_name}")
            if not os.path.exists(key_path):
                return {
                    "success": False,
                    "error": f"SSH key not found: {key_path}",
                    "key_path": key_path,
                }

            # Connect to server (support both key-based and password authentication)
            connect_kwargs = {
                "hostname": host,
                "username": username,
                "port": port,
                "timeout": 30,
            }

            if password:
                # Use password authentication
                connect_kwargs["password"] = password
                auth_method = "password"
            else:
                # Use key-based authentication
                connect_kwargs["key_filename"] = key_path
                auth_method = "key"

            self.ssh_client.connect(**connect_kwargs)

            self.connected = True
            self.connected_username = username
            self.default_working_dir = working_dir
            self.launch_agents_dir = launch_agents_dir
            logger.info(f"✅ Connected to {host}")

            return {
                "success": True,
                "message": f"Connected to {host} as {username}",
                "host": host,
                "username": username,
                "working_dir": working_dir,
                "launch_agents_dir": launch_agents_dir,
                "key_path": key_path if not password else None,
                "auth_method": auth_method,
                "deployment_type": deployment_type,
                "docker_image": docker_image,
                "docker_compose_file": docker_compose_file,
            }

        except Exception as e:
            logger.error(f"❌ Failed to connect to {host}: {e}")
            return {"success": False, "error": str(e)}

    async def execute_command(
        self, command: str, working_dir: str = None, custom_command: str = None
    ) -> Dict[str, Any]:
        """Execute a command on the server - SECURITY: Only restart.sh execution allowed"""
        if not self.connected or not self.ssh_client:
            return {"success": False, "error": "Not connected to server"}

        # Debug logging for working directory
        logger.info(f"🔍 execute_command called with working_dir: {working_dir}")
        logger.info(f"🔍 self.default_working_dir: {getattr(self, 'default_working_dir', 'NOT_SET')}")

        # SECURITY: Block all commands except restart.sh execution
        # Only allow the restart.sh script to be executed - all other commands are blocked
        if custom_command:
            # Temporarily allow update_scripts.sh for updating restart scripts
            if custom_command == "./update_scripts.sh":
                logger.info("🔧 Allowing update_scripts.sh for script updates...")
                actual_command = custom_command
            else:
                return {
                    "success": False,
                    "error": "SECURITY: Custom commands are blocked. Only restart.sh execution is allowed.",
                    "blocked_command": custom_command,
                    "allowed_operation": "run_restart",
                }

        # Only allow restart script execution (Linux production - use deployment/restart.sh)
        safe_commands = {
            "run_restart": "./deployment/restart.sh",
            "run_restart_force": "./deployment/restart.sh --force",
        }

        # Map intent to actual command
        actual_command = safe_commands.get(command)
        if not actual_command:
            return {
                "success": False,
                "error": f"SECURITY: Command '{command}' not allowed. Only restart script execution is permitted.",
                "allowed_operation": "run_restart",
                "note": "All other commands must be added to restart script",
            }

        command_type = "restart_only"

        try:
            if command_type == "custom":
                logger.info(f"🔧 Executing custom command: {actual_command}")
            else:
                logger.info(
                    f"🔧 Executing safe operation: {command} -> {actual_command}"
                )

            # Always use the working directory for security
            working_dir = working_dir or getattr(
                self, "default_working_dir", "/home/joebert/open-data-visualization"
            )

            # Expand tilde if present (for remote server)
            if working_dir.startswith("~/"):
                # For remote server, we need to expand ~ to the user's home directory
                # This will be expanded on the remote server side
                expanded_working_dir = working_dir
            else:
                expanded_working_dir = working_dir

            # Use working directory directly
            full_command = f"cd {expanded_working_dir} && {actual_command}"
            logger.info(f"📁 Working directory: {working_dir} (expanded: {expanded_working_dir})")

            # Execute command
            stdin, stdout, stderr = self.ssh_client.exec_command(full_command)

            # Get output
            output = stdout.read().decode("utf-8").strip()
            error = stderr.read().decode("utf-8").strip()
            exit_code = stdout.channel.recv_exit_status()

            logger.info(f"📤 Operation result: {output}")
            if error:
                logger.warning(f"⚠️ Operation warnings: {error}")

            return {
                "success": exit_code == 0,
                "operation": command,
                "command_type": command_type,
                "actual_command": actual_command,
                "output": output,
                "error": error,
                "exit_code": exit_code,
                "working_dir": working_dir,
            }

        except Exception as e:
            logger.error(f"❌ Safe operation failed: {e}")
            return {"success": False, "error": str(e), "operation": command}

    async def deploy_restart(
        self,
        working_dir: str = "/home/joebert/open-data-visualization",
        custom_command: str = None,
        deployment_type: str = "script",
        docker_image: str = None,
        docker_compose_file: str = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Deploy and restart the application - AI-first, secure deployment with multiple deployment types"""
        try:
            if custom_command:
                logger.info(f"🚀 Starting custom command execution: {custom_command}")
            else:
                logger.info(
                    f"🚀 Starting AI-first, secure {deployment_type} deployment..."
                )

            # SECURITY: Always use the specified working directory
            working_dir = working_dir or getattr(
                self, "default_working_dir", "/home/joebert/open-data-visualization"
            )

            # First, fix git state if there are divergent branches (handle force-pushed history)
            logger.info("🔧 Step 0: Fixing git state (if needed)...")
            git_fix_command = f"cd {working_dir} && git fetch origin && git reset --hard origin/main"
            stdin, stdout, stderr = self.ssh_client.exec_command(git_fix_command)
            git_output = stdout.read().decode("utf-8").strip()
            git_error = stderr.read().decode("utf-8").strip()
            git_exit = stdout.channel.recv_exit_status()
            if git_exit == 0:
                logger.info(f"✅ Git state fixed: {git_output}")
            else:
                logger.warning(f"⚠️ Git fix warning (may be normal if already in sync): {git_error}")

            # If custom command is specified, execute it directly
            if custom_command:
                logger.info("🔧 Executing custom command directly...")
                result = await self.execute_command(
                    "custom", working_dir, custom_command
                )

                return {
                    "success": result["success"],
                    "output": result["output"],
                    "error": result["error"],
                    "exit_code": result["exit_code"],
                    "custom_command": custom_command,
                    "execution_time": datetime.now().isoformat(),
                    "working_dir": working_dir,
                }

            # Handle different deployment types
            if deployment_type == "docker":
                return await self._deploy_docker(
                    working_dir, docker_image, docker_compose_file
                )
            elif deployment_type == "kubernetes":
                return await self._deploy_kubernetes(working_dir)
            else:
                # Default script-based deployment
                return await self._deploy_script(working_dir, force)

        except Exception as e:
            logger.error(f"❌ AI-first deployment failed: {e}")
            return {"success": False, "error": str(e), "step": "deployment_execution"}

    async def _deploy_script(
        self, working_dir: str, force: bool = False
    ) -> Dict[str, Any]:
        """Deploy using script-based approach (default) - Only restart script execution allowed"""
        try:
            # SECURITY: Only restart script execution is allowed
            # All other operations must be included in restart script

            # Step 1: Execute restart script (main deployment operation)
            if force:
                logger.info("🚀 Step 1: Executing restart script with FORCE option...")
                restart_result = await self.execute_command(
                    "run_restart_force", working_dir
                )
            else:
                logger.info("🚀 Step 1: Executing restart script...")
                restart_result = await self.execute_command("run_restart", working_dir)

            return {
                "success": restart_result["success"],
                "output": restart_result["output"],
                "error": restart_result["error"],
                "exit_code": restart_result["exit_code"],
                "deployment_time": datetime.now().isoformat(),
                "deployment_type": "script",
                "steps_completed": ["restart_execution"],
                "working_dir": working_dir,
                "note": "All deployment operations are now handled by restart script",
            }

        except Exception as e:
            logger.error(f"❌ Script deployment failed: {e}")
            return {"success": False, "error": str(e), "step": "script_deployment"}

    async def deploy_fast(
        self, working_dir: str = "/home/joebert/open-data-visualization"
    ) -> Dict[str, Any]:
        """Fast deployment - Only restart script execution allowed"""
        try:
            logger.info("⚡ Starting fast deployment (restart script only)...")

            # SECURITY: Only restart script execution is allowed
            # All other operations must be included in restart script

            # Step 1: Execute restart script (main deployment operation)
            logger.info("🚀 Step 1: Executing restart script...")
            restart_result = await self.execute_command("run_restart", working_dir)

            logger.info("✅ Fast deployment completed successfully!")

            return {
                "success": restart_result["success"],
                "output": restart_result["output"],
                "error": restart_result["error"],
                "exit_code": restart_result["exit_code"],
                "deployment_time": datetime.now().isoformat(),
                "deployment_type": "fast_script",
                "steps_completed": ["restart_execution"],
                "working_dir": working_dir,
                "note": "All deployment operations are now handled by restart script",
            }

        except Exception as e:
            logger.error(f"❌ Fast deployment failed: {e}")
            return {"success": False, "error": str(e), "step": "fast_deployment"}

    async def _deploy_docker(
        self,
        working_dir: str,
        docker_image: str = None,
        docker_compose_file: str = None,
    ) -> Dict[str, Any]:
        """Deploy using Docker (future implementation)"""
        try:
            logger.info("🐳 Docker deployment not yet implemented")
            return {
                "success": False,
                "error": "Docker deployment is planned for future implementation",
                "deployment_type": "docker",
                "working_dir": working_dir,
                "docker_image": docker_image,
                "docker_compose_file": docker_compose_file,
            }
        except Exception as e:
            logger.error(f"❌ Docker deployment failed: {e}")
            return {"success": False, "error": str(e), "step": "docker_deployment"}

    async def _deploy_kubernetes(self, working_dir: str) -> Dict[str, Any]:
        """Deploy using Kubernetes (future implementation)"""
        try:
            logger.info("☸️ Kubernetes deployment not yet implemented")
            return {
                "success": False,
                "error": "Kubernetes deployment is planned for future implementation",
                "deployment_type": "kubernetes",
                "working_dir": working_dir,
            }
        except Exception as e:
            logger.error(f"❌ Kubernetes deployment failed: {e}")
            return {"success": False, "error": str(e), "step": "kubernetes_deployment"}

    async def deploy_visualization(
        self,
        working_dir: str = "/home/joebert/open-data-visualization",
        force_restart: bool = False,
    ) -> Dict[str, Any]:
        """Deploy BetterGovPH Open Data Visualization - uses integrated restart.sh for reliability"""
        try:
            logger.info("🚀 Starting BetterGovPH Visualization deployment...")

            # Use the proven restart.sh script for deployment
            # This ensures all steps are executed correctly on the remote server
            restart_command = "./restart.sh"
            if force_restart:
                restart_command += " --force"

            logger.info(f"⚙️ Executing deployment: {restart_command}")

            result = await self.execute_command("deploy_visualization", working_dir, restart_command)

            if result["success"]:
                logger.info("✅ BetterGovPH Visualization deployment completed successfully!")
                return {
                    "success": True,
                    "message": "BetterGovPH Visualization deployment completed successfully",
                    "command": restart_command,
                    "output": result["output"],
                    "production_url": "https://visualizations.bettergov.ph",
                    "deployment_time": datetime.now().isoformat(),
                    "working_dir": working_dir,
                }
            else:
                logger.error("❌ BetterGovPH deployment failed")
                return {
                    "success": False,
                    "error": "Deployment command failed",
                    "command": restart_command,
                    "output": result["output"],
                    "error_output": result["error"],
                    "step": "deployment_failed",
                    "working_dir": working_dir,
                }

        except Exception as e:
            logger.error(f"❌ BetterGovPH deployment failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "step": "deployment_failed",
                "working_dir": working_dir,
            }

    async def _run_precheck(self, working_dir: str = None) -> Dict[str, Any]:
        """Run pre-check operations before deployment"""
        try:
            logger.info("🔍 Starting pre-check operations...")

            # Step 1: Run pre-push check script
            logger.info("📋 Step 1: Running pre-push check script...")
            import subprocess
            import os

            # Use local project directory for pre-check (not remote working directory)
            local_project_dir = "/home/joebert/open-data-visualization"
            precheck_script = os.path.join(local_project_dir, "deployment", "pre_push_check.sh")
            if not os.path.exists(precheck_script):
                return {
                    "success": False,
                    "error": f"Pre-check script not found in local project directory: {local_project_dir}",
                    "step": "script_check",
                    "searched_path": precheck_script,
                }

            # Run pre-push check
            try:
                # Use local project directory for git operations
                git_work_dir = local_project_dir
                logger.info(f"📁 Git working directory: {git_work_dir}")

                result = subprocess.run(
                    [f"{git_work_dir}/deployment/pre_push_check.sh"],
                    capture_output=True,
                    text=True,
                    cwd=git_work_dir,
                    timeout=60,
                )

                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Pre-push check failed with exit code {result.returncode}",
                        "step": "pre_push_check",
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }

                logger.info("✅ Pre-push check passed")

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": "Pre-push check timed out after 60 seconds",
                    "step": "pre_push_check",
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Pre-push check execution failed: {str(e)}",
                    "step": "pre_push_check",
                }

            # Step 2: Git add, commit, and push
            logger.info("📝 Step 2: Running git operations...")

            # Git add
            try:
                add_result = subprocess.run(
                    ["git", "add", "."],
                    capture_output=True,
                    text=True,
                    cwd=git_work_dir,
                    timeout=30,
                )

                if add_result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Git add failed: {add_result.stderr}",
                        "step": "git_add",
                    }

                logger.info("✅ Git add completed")

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Git add failed: {str(e)}",
                    "step": "git_add",
                }

            # Git commit
            try:
                commit_result = subprocess.run(
                    ["git", "commit", "-m", "Auto-commit before deployment"],
                    capture_output=True,
                    text=True,
                    cwd=git_work_dir,
                    timeout=30,
                )

                if commit_result.returncode != 0:
                    # Check if there's nothing to commit
                    if "nothing to commit" in commit_result.stdout.lower():
                        logger.info("ℹ️ Nothing to commit")
                    else:
                        return {
                            "success": False,
                            "error": f"Git commit failed: {commit_result.stderr}",
                            "step": "git_commit",
                        }
                else:
                    logger.info("✅ Git commit completed")

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Git commit failed: {str(e)}",
                    "step": "git_commit",
                }

            # Git push
            try:
                push_result = subprocess.run(
                    ["git", "push"],
                    capture_output=True,
                    text=True,
                    cwd=git_work_dir,
                    timeout=60,
                )

                if push_result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Git push failed: {push_result.stderr}",
                        "step": "git_push",
                    }

                logger.info("✅ Git push completed")

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Git push failed: {str(e)}",
                    "step": "git_push",
                }

            return {
                "success": True,
                "message": "Pre-check completed successfully",
                "steps_completed": [
                    "pre_push_check",
                    "git_add",
                    "git_commit",
                    "git_push",
                ],
                "precheck_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"❌ Pre-check failed: {e}")
            return {"success": False, "error": str(e), "step": "precheck_execution"}

    async def git_pull(
        self, working_dir: str = "/home/joebert/open-data-visualization"
    ) -> Dict[str, Any]:
        """Pull latest changes from git - AI-first, secure git operation"""
        try:
            logger.info("📥 Starting AI-first, secure git pull...")

            # SECURITY: Always use the specified working directory
            working_dir = working_dir or getattr(
                self, "default_working_dir", "/home/joebert/open-data-visualization"
            )

            # Step 1: Check git status first
            logger.info("📋 Step 1: Checking git status...")
            status_result = await self.execute_command("check_git_status", working_dir)
            if not status_result["success"]:
                return {
                    "success": False,
                    "error": f"Git status check failed: {status_result['error']}",
                    "step": "git_status_check",
                }

            # Step 2: Pull latest changes (secure operation)
            logger.info("📥 Step 2: Pulling latest changes...")
            pull_result = await self.execute_command("pull_latest", working_dir)

            return {
                "success": pull_result["success"],
                "output": pull_result["output"],
                "error": pull_result["error"],
                "exit_code": pull_result["exit_code"],
                "git_status_before": status_result["output"],
                "pull_time": datetime.now().isoformat(),
                "working_dir": working_dir,
            }

        except Exception as e:
            logger.error(f"❌ AI-first git pull failed: {e}")
            return {"success": False, "error": str(e), "step": "git_pull_execution"}

    async def check_status(
        self, working_dir: str = "/home/joebert/open-data-visualization"
    ) -> Dict[str, Any]:
        """Check deployment status - AI-first, secure status monitoring"""
        try:
            logger.info("📊 Starting AI-first, secure status check...")

            # SECURITY: Always use the specified working directory
            working_dir = working_dir or getattr(
                self, "default_working_dir", "/home/joebert/open-data-visualization"
            )

            # Step 1: Verify working directory
            logger.info("📁 Step 1: Verifying working directory...")
            dir_result = await self.execute_command("check_directory", working_dir)
            if not dir_result["success"]:
                return {
                    "success": False,
                    "error": f"Working directory verification failed: {dir_result['error']}",
                    "step": "directory_verification",
                }

            # Step 2: Check git status (secure operation)
            logger.info("📋 Step 2: Checking git status...")
            git_status = await self.execute_command("check_git_status", working_dir)

            # Step 3: Check running processes (secure operation)
            logger.info("🔄 Step 3: Checking running processes...")
            process_check = await self.execute_command("check_processes", working_dir)

            # Step 4: Check disk space (secure operation)
            logger.info("💾 Step 4: Checking disk space...")
            disk_check = await self.execute_command("check_disk_space", working_dir)

            # Compile comprehensive status report
            status_report = {
                "success": True,
                "working_dir": working_dir,
                "check_time": datetime.now().isoformat(),
                "git_status": git_status.get("output", "Unknown"),
                "processes": process_check.get("output", "No processes found"),
                "disk_space": disk_check.get("output", "Unknown"),
                "steps_completed": [
                    "directory_verification",
                    "git_status",
                    "process_check",
                    "disk_check",
                ],
            }

            # Add warnings if any operations failed
            warnings = []
            if not git_status["success"]:
                warnings.append(f"Git status check failed: {git_status['error']}")
            if not process_check["success"]:
                warnings.append(f"Process check failed: {process_check['error']}")
            if not disk_check["success"]:
                warnings.append(f"Disk check failed: {disk_check['error']}")

            if warnings:
                status_report["warnings"] = warnings

            return status_report

        except Exception as e:
            logger.error(f"❌ AI-first status check failed: {e}")
            return {"success": False, "error": str(e), "step": "status_check_execution"}

    async def sanity_test(
        self,
        base_url: str = "https://visualizations.bettergov.ph",
        working_dir: str = "/home/joebert/open-data-visualization"
    ) -> Dict[str, Any]:
        """Run comprehensive sanity tests on deployed services"""
        try:
            logger.info(f"🧪 Starting comprehensive sanity tests on {base_url}...")

            # SECURITY: Always use the specified working directory
            working_dir = working_dir or getattr(
                self, "default_working_dir", "/home/joebert/open-data-visualization"
            )

            # Define test endpoints for BetterGovPH visualization API
            test_endpoints = [
                {"path": "/", "name": "API Root", "expected_status": [200]},
                {"path": "/api/budget/analysis/comparison-chart", "name": "Budget vs NEP Chart", "expected_status": [200]},
                {"path": "/api/flood/health", "name": "Flood Health Check", "expected_status": [200]},
                {"path": "/api/dime/statistics", "name": "DIME Statistics", "expected_status": [200]},
            ]

            results = {
                "base_url": base_url,
                "total_tests": len(test_endpoints),
                "passed": 0,
                "failed": 0,
                "test_results": [],
                "overall_success": True,
                "test_time": datetime.now().isoformat()
            }

            # Run tests
            for endpoint in test_endpoints:
                test_result = await self._test_endpoint(base_url, endpoint)
                results["test_results"].append(test_result)

                if test_result["success"]:
                    results["passed"] += 1
                    logger.info(f"✅ {endpoint['name']}: {test_result['status']} ({test_result['response_time']}ms)")
                else:
                    results["failed"] += 1
                    results["overall_success"] = False
                    logger.warning(f"⚠️ {endpoint['name']}: {test_result['error']}")

            # Summary
            logger.info(f"🧪 Sanity test summary: {results['passed']}/{results['total_tests']} passed")

            if results["overall_success"]:
                logger.info("✅ All sanity tests passed!")
            else:
                logger.warning(f"⚠️ {results['failed']} sanity test(s) failed")

            return {
                "success": results["overall_success"],
                "message": f"Sanity tests completed: {results['passed']}/{results['total_tests']} passed",
                "results": results,
                "working_dir": working_dir
            }

        except Exception as e:
            logger.error(f"❌ Sanity test failed: {e}")
            return {"success": False, "error": str(e), "step": "sanity_test_execution"}

    async def _test_endpoint(self, base_url: str, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """Test a single endpoint"""
        import aiohttp
        import time

        url = f"{base_url}{endpoint['path']}"
        start_time = time.time()

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(url, allow_redirects=True) as response:
                    response_time = int((time.time() - start_time) * 1000)

                    if response.status in endpoint['expected_status']:
                        return {
                            "success": True,
                            "endpoint": endpoint['path'],
                            "name": endpoint['name'],
                            "status": response.status,
                            "response_time": response_time,
                            "url": url
                        }
                    else:
                        return {
                            "success": False,
                            "endpoint": endpoint['path'],
                            "name": endpoint['name'],
                            "status": response.status,
                            "response_time": response_time,
                            "url": url,
                            "error": f"Unexpected status {response.status}, expected {endpoint['expected_status']}"
                        }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "endpoint": endpoint['path'],
                "name": endpoint['name'],
                "error": "Request timeout (10s)",
                "url": url
            }
        except Exception as e:
            return {
                "success": False,
                "endpoint": endpoint['path'],
                "name": endpoint['name'],
                "error": str(e),
                "url": url
            }

    async def disconnect(self) -> Dict[str, Any]:
        """Disconnect from server"""
        try:
            if self.ssh_client:
                self.ssh_client.close()
                self.connected = False
                logger.info("🔌 Disconnected from server")

            return {"success": True, "message": "Disconnected from server"}

        except Exception as e:
            logger.error(f"❌ Disconnect failed: {e}")
            return {"success": False, "error": str(e)}


class DeploymentMCP:
    """MCP handler for deployment requests"""

    def __init__(self):
        self.server = DeploymentMCPServer()

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP requests"""
        method = request.get("method")
        params = request.get("params", {})

        logger.info(f"🔧 Handling request: {method}")

        try:
            if method == "connect_to_server":
                return await self.server.connect_to_server(
                    host=params.get("host", "10.27.79.7"),
                    username=params.get("username", "joebert"),
                    key_name=params.get("key_name", "klti"),
                    port=params.get("port", 22),
                    working_dir=params.get("working_dir", "/home/joebert/open-data-visualization"),
                    password=params.get("password"),
                    deployment_type=params.get("deployment_type", "script"),
                    docker_image=params.get("docker_image"),
                    docker_compose_file=params.get("docker_compose_file"),
                    run_precheck=params.get("run_precheck", True),
                    launch_agents_dir=params.get("launch_agents_dir", "/home/joebert/.config/systemd/user/"),
                )

            elif method == "execute_command":
                return await self.server.execute_command(
                    command=params.get("command"),
                    working_dir=params.get("working_dir"),
                    custom_command=params.get("custom_command"),
                )

            elif method == "deploy_restart":
                return await self.server.deploy_restart(
                    working_dir=params.get("working_dir", "/home/joebert/open-data-visualization"),
                    custom_command=params.get("custom_command"),
                    deployment_type=params.get("deployment_type", "script"),
                    docker_image=params.get("docker_image"),
                    docker_compose_file=params.get("docker_compose_file"),
                    force=params.get("force", False),
                )

            elif method == "deploy_fast":
                return await self.server.deploy_fast(
                    working_dir=params.get("working_dir", "/home/joebert/open-data-visualization")
                )

            elif method == "deploy_visualization":
                return await self.server.deploy_visualization(
                    working_dir=params.get("working_dir", "/home/joebert/open-data-visualization"),
                    force_restart=params.get("force_restart", False),
                )

            elif method == "git_pull":
                return await self.server.git_pull(
                    working_dir=params.get("working_dir", "/home/joebert/open-data-visualization")
                )

            elif method == "check_status":
                return await self.server.check_status(
                    working_dir=params.get("working_dir", "/home/joebert/open-data-visualization")
                )

            elif method == "sanity_test":
                return await self.server.sanity_test(
                    base_url=params.get("base_url", "https://visualizations.bettergov.ph"),
                    working_dir=params.get("working_dir", "/home/joebert/open-data-visualization")
                )

            elif method == "disconnect":
                return await self.server.disconnect()

            else:
                return {"success": False, "error": f"Unknown method: {method}"}

        except Exception as e:
            logger.error(f"❌ Request handling failed: {e}")
            return {"success": False, "error": str(e)}


async def main():
    """Main function for testing"""
    mcp = DeploymentMCP()

    # Example deployment workflow
    print("🚀 Testing BetterGovPH Deployment MCP...")

    # Connect to server
    connect_result = await mcp.handle_request(
        {
            "method": "connect_to_server",
            "params": {
                "host": "10.27.79.7",
                "username": "joebert",
                "key_name": "klti",
            },
        }
    )

    if connect_result["success"]:
        print("✅ Connected to server")

        # Check status
        status_result = await mcp.handle_request(
            {
                "method": "check_status",
                "params": {"working_dir": "/home/joebert/open-data-visualization"},
            }
        )

        if status_result["success"]:
            print("✅ Status check completed")
            print(f"Git status: {status_result['git_status']}")

        # Deploy and restart
        deploy_result = await mcp.handle_request(
            {
                "method": "deploy_restart",
                "params": {"working_dir": "/home/joebert/open-data-visualization"},
            }
        )

        if deploy_result["success"]:
            print("✅ Deployment completed")
        else:
            print(f"❌ Deployment failed: {deploy_result['error']}")

        # Disconnect
        await mcp.handle_request({"method": "disconnect"})
        print("✅ Disconnected from server")

    else:
        print(f"❌ Connection failed: {connect_result['error']}")


async def deploy_visualization(
    host: str = "10.27.79.7",
    username: str = "joebert",
    working_dir: str = "/home/joebert/open-data-visualization",
) -> bool:
    """Deploy BetterGovPH Open Data Visualization using integrated MCP method"""
    try:
        print(f"🚀 Starting BetterGovPH Visualization deployment to {host}...")

        # Connect
        mcp = DeploymentMCP()
        connect_result = await mcp.handle_request(
            {"method": "connect_to_server", "params": {"host": host, "username": username}}
        )

        if not connect_result["success"]:
            print(f"❌ Connection failed: {connect_result['error']}")
            return False

        print("✅ Connected to server")

        # Deploy using the integrated visualization method
        deploy_result = await mcp.handle_request(
            {"method": "deploy_visualization", "params": {"working_dir": working_dir}}
        )

        if deploy_result["success"]:
            print("✅ BetterGovPH Visualization deployment completed successfully!")
            print(f"🌐 Frontend: {deploy_result.get('production_url', 'N/A')}")
            return True
        else:
            print(f"❌ Deployment failed: {deploy_result['error']}")
            return False

        # Disconnect
        await mcp.handle_request({"method": "disconnect"})

    except Exception as e:
        print(f"❌ Deployment error: {e}")
        return False


async def run_sanity_test(
    host: str = "10.27.79.7",
    username: str = "joebert",
    working_dir: str = "/home/joebert/open-data-visualization",
    base_url: str = "https://visualizations.bettergov.ph",
) -> bool:
    """Run sanity tests on deployed services"""
    mcp = DeploymentMCP()

    # Connect to server
    connect_result = await mcp.handle_request(
        {
            "method": "connect_to_server",
            "params": {
                "host": host,
                "username": username,
                "working_dir": working_dir,
                "run_precheck": False,  # Skip precheck for sanity tests only
            },
        }
    )

    if not connect_result["success"]:
        print(f"❌ Failed to connect to {host}: {connect_result['error']}")
        return False

    print(f"✅ Connected to {host}")

    # Run sanity tests
    test_result = await mcp.handle_request(
        {
            "method": "sanity_test",
            "params": {
                "base_url": base_url,
                "working_dir": working_dir,
            },
        }
    )

    # Disconnect
    await mcp.handle_request({"method": "disconnect"})

    if test_result["success"]:
        print(f"✅ Sanity tests completed successfully!")
        return True
    else:
        print(f"❌ Sanity tests failed: {test_result.get('error', 'Unknown error')}")
        return False


async def deploy_with_options(
    host: str = "10.27.79.7",
    username: str = "joebert",
    working_dir: str = "/home/joebert/open-data-visualization",
    launch_agents_dir: str = "/home/joebert/.config/systemd/user/",
    fast: bool = False,
    force: bool = False,
    base_url: str = "https://visualizations.bettergov.ph",
    no_precheck: bool = False
):
    """Deploy with options - fast, full, or forced deployment"""
    mcp = DeploymentMCP()

    print(f"🚀 Starting deployment to {host}...")
    print(f"🔍 deploy_with_options working_dir: {working_dir}")

    # Connect to server
    connect_result = await mcp.handle_request(
        {
            "method": "connect_to_server",
            "params": {"host": host, "username": username, "key_name": "klti", "working_dir": working_dir, "launch_agents_dir": launch_agents_dir, "run_precheck": not no_precheck},
        }
    )

    if not connect_result["success"]:
        print(f"❌ Connection failed: {connect_result['error']}")
        return False

    print("✅ Connected to server")

    # Choose deployment method
    method = "deploy_fast" if fast else "deploy_restart"
    deployment_name = "FAST" if fast else "FULL"

    print(f"🔧 Starting {deployment_name} deployment...")

    # Deploy
    deploy_params = {"working_dir": working_dir}
    if force and method == "deploy_restart":
        deploy_params["force"] = True

    deploy_result = await mcp.handle_request(
        {"method": method, "params": deploy_params}
    )

    if deploy_result["success"]:
        print(f"✅ {deployment_name} deployment completed successfully!")
        
        # Disconnect after deployment
        await mcp.handle_request({"method": "disconnect"})
        return True
    else:
        print(f"❌ {deployment_name} deployment failed: {deploy_result['error']}")
        # Disconnect on failure
        await mcp.handle_request({"method": "disconnect"})
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BetterGovPH Open Data Visualization Deployment Tool")
    parser.add_argument(
        "--host",
        default="10.27.79.7",
        help="Target host (default: 10.27.79.7 for production)",
    )
    parser.add_argument(
        "--user",
        default="joebert",
        help="SSH username (default: joebert for production)",
    )
    parser.add_argument(
        "--dir",
        default="/home/joebert/open-data-visualization",
        help="Working directory on target server (default: /home/joebert/open-data-visualization)",
    )
    parser.add_argument(
        "--launch-agents-dir",
        default="/home/joebert/.config/systemd/user/",
        help="Systemd user directory on Linux (default: /home/joebert/.config/systemd/user/)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use fast deployment (skip service monitoring)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force deployment (skip file age checks, but NEVER bypass pre-check)",
    )
    parser.add_argument(
        "--no-precheck",
        action="store_true",
        help="Skip pre-check entirely (use with caution)",
    )
    parser.add_argument(
        "--base-url",
        default="https://visualizations.bettergov.ph",
        help="Base URL for sanity testing (default: https://visualizations.bettergov.ph)",
    )
    args = parser.parse_args()

    # Default action is deploy
    success = asyncio.run(
        deploy_with_options(host=args.host, username=args.user, working_dir=args.dir, fast=args.fast, force=args.force, base_url=args.base_url, no_precheck=args.no_precheck)
    )
    exit(0 if success else 1)
