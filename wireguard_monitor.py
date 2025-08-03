#!/usr/bin/env python3
"""
WireGuard Connection Monitor
Monitors WireGuard connections via API and sends email notifications when connections fail.
"""

import requests
import smtplib
import json
import time
import logging
import os
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def setup_logging(verbose=False, debug=False):
    """Setup logging configuration based on verbosity level."""
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Choose formatter based on debug mode
    formatter = detailed_formatter if debug else simple_formatter
    
    # Setup handlers
    handlers = [logging.StreamHandler()]
    
    # Add file handler if not in debug mode (avoid cluttering during testing)
    if not debug:
        handlers.append(logging.FileHandler('wireguard_monitor.log'))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    # Apply detailed formatter to all handlers in debug mode
    if debug:
        for handler in logging.getLogger().handlers:
            handler.setFormatter(detailed_formatter)
    
    return logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Monitor WireGuard connections and send email notifications',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 wireguard_monitor.py                    # Normal operation
  python3 wireguard_monitor.py -v                 # Verbose output
  python3 wireguard_monitor.py -d                 # Debug mode with detailed logging
  python3 wireguard_monitor.py --test-email       # Test email configuration
  python3 wireguard_monitor.py --check-once       # Single status check (no loop)
        """
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging (INFO level)'
    )
    
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug logging (DEBUG level) with detailed output'
    )
    
    parser.add_argument(
        '--test-email',
        action='store_true',
        help='Send a test email and exit'
    )
    
    parser.add_argument(
        '--check-once',
        action='store_true',
        help='Perform a single status check and exit (useful for testing)'
    )
    
    parser.add_argument(
        '--config-test',
        action='store_true',
        help='Test configuration and API connectivity without sending emails'
    )
    
    return parser.parse_args()

def load_config() -> Dict:
    """Load configuration from environment variables."""
    
    # Parse email recipients (comma-separated)
    to_emails_str = os.getenv('TO_EMAILS', 'admin@example.com')
    to_emails = [email.strip() for email in to_emails_str.split(',')]
    
    # Parse monitored peers (comma-separated)
    monitored_peers_str = os.getenv('MONITORED_PEERS', '')
    monitored_peers = [peer.strip() for peer in monitored_peers_str.split(',') if peer.strip()]
    
    return {
        # WireGuard API settings
        'api_url': os.getenv('WG_API_URL', 'http://localhost:10086/api'),
        'api_key': os.getenv('WG_API_KEY'),
        'config_name': os.getenv('WG_CONFIG_NAME', 'wg0'),
        
        # Email settings
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', '587')),
        'smtp_username': os.getenv('SMTP_USERNAME'),
        'smtp_password': os.getenv('SMTP_PASSWORD'),
        'from_email': os.getenv('FROM_EMAIL'),
        'to_emails': to_emails,
        
        # Monitoring settings
        'check_interval': int(os.getenv('CHECK_INTERVAL', '300')),
        'connection_timeout': int(os.getenv('CONNECTION_TIMEOUT', '10')),
        'max_retries': int(os.getenv('MAX_RETRIES', '3')),
        'retry_delay': int(os.getenv('RETRY_DELAY', '30')),
        'handshake_timeout': int(os.getenv('HANDSHAKE_TIMEOUT', '300')),
        'monitored_peers': monitored_peers,
        'monitor_all_peers': os.getenv('MONITOR_ALL_PEERS', 'false').lower() == 'true',
    }

# Load configuration
CONFIG = load_config()

# Initialize logger (will be reconfigured in main())
logger = logging.getLogger(__name__)

class EmailNotifier:
    """Handles email notifications for WireGuard monitoring."""
    
    def __init__(self, email_config: Dict):
        """Initialize email notifier with configuration."""
        self.config = email_config
        self.logger = logging.getLogger(__name__)
    
    def send_notification(self, subject: str, body: str):
        """Send email notification."""
        try:
            self.logger.debug(f"Preparing email: {subject}")
            self.logger.debug(f"SMTP server: {self.config['smtp_server']}:{self.config['smtp_port']}")
            self.logger.debug(f"From: {self.config['from_email']}")
            self.logger.debug(f"To: {self.config['to_emails']}")
            
            msg = MIMEMultipart()
            msg['From'] = self.config['from_email']
            msg['To'] = ', '.join(self.config['to_emails'])
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            self.logger.debug("Connecting to SMTP server...")
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            
            self.logger.debug("Starting TLS...")
            server.starttls()
            
            self.logger.debug("Authenticating...")
            server.login(self.config['smtp_username'], self.config['smtp_password'])
            
            self.logger.debug("Sending email...")
            for to_email in self.config['to_emails']:
                server.sendmail(self.config['from_email'], to_email, msg.as_string())
            
            server.quit()
            self.logger.info(f"Email notification sent: {subject}")
            
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")
            self.logger.debug(f"Email error details: {type(e).__name__}: {str(e)}")
    
    def send_test_email(self, config_name: str, api_url: str, check_interval: int):
        """Send a test email to verify configuration."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        subject = "WireGuard Monitor Test Email"
        body = f"""
This is a test email from WireGuard Monitor.

Configuration Test Results:
- Timestamp: {timestamp}
- Monitoring config: {config_name}
- API URL: {api_url}
- Check interval: {check_interval} seconds

If you receive this email, your email configuration is working correctly!
"""
        
        self.logger.info("Sending test email...")
        self.send_notification(subject, body)

class WireGuardMonitor:
    def __init__(self, config: Dict, email_notifier: EmailNotifier):
        self.config = config
        self.email_notifier = email_notifier
        self.last_status = {}  # Track last known status to avoid spam
        self.consecutive_failures = 0
        
    def get_wireguard_status(self) -> Optional[Dict]:
        """Fetch WireGuard configuration info from API."""
        headers = {
            'wg-dashboard-apikey': self.config['api_key']
        }
        
        url = f"{self.config['api_url']}/getWireguardConfigurationInfo"
        params = {'configurationName': self.config['config_name']}
        
        logger.debug(f"Making API request to: {url}")
        logger.debug(f"Request params: {params}")
        logger.debug(f"Request headers: {dict(headers)}")  # Hide sensitive API key in non-debug mode
        
        for attempt in range(self.config['max_retries']):
            try:
                logger.debug(f"API request attempt {attempt + 1}/{self.config['max_retries']}")
                
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=self.config['connection_timeout']
                )
                
                logger.debug(f"API response status: {response.status_code}")
                logger.debug(f"API response headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.debug(f"API response data: {json.dumps(data, indent=2)}")
                    return data
                else:
                    logger.warning(f"API returned status {response.status_code}: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"API request attempt {attempt + 1} failed: {e}")
                logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")
                
                if attempt < self.config['max_retries'] - 1:
                    logger.debug(f"Waiting {self.config['retry_delay']} seconds before retry...")
                    time.sleep(self.config['retry_delay'])
        
        logger.error("All API request attempts failed")
        return None
    
    def analyze_connections(self, data: Dict) -> Dict[str, bool]:
        """Analyze connection data and return status for each peer."""
        logger.debug("Starting connection analysis")
        
        if not data or 'data' not in data:
            logger.error("Invalid API response format")
            logger.debug(f"Received data: {data}")
            return {}
        
        config_data = data['data']
        logger.debug(f"Configuration data keys: {list(config_data.keys())}")
        
        # Check if the interface is up (correct field name from API)
        interface_info = config_data.get('configurationInfo', {})
        interface_status = interface_info.get('Status', False)
        logger.debug(f"Interface status: {interface_status} (raw: {interface_info.get('Status')})")
        
        if not interface_status:
            logger.warning(f"WireGuard interface {self.config['config_name']} is down")
            return {'interface': False}
        
        # Check peers (correct field name from API)
        peers = config_data.get('configurationPeers', [])
        logger.debug(f"Found {len(peers)} total peers")
        
        if not peers:
            logger.warning("No peers found in configuration")
            return {'interface': True, 'peers': {}}
        
        # Determine which peers to monitor
        if self.config['monitored_peers']:
            peers_to_monitor = self.config['monitored_peers']
            logger.debug(f"Monitoring specific peers: {peers_to_monitor}")
        elif self.config['monitor_all_peers']:
            peers_to_monitor = [peer.get('name', f"peer-{i}") for i, peer in enumerate(peers)]
            logger.debug(f"Monitoring all peers: {peers_to_monitor}")
        else:
            logger.warning("No peers configured for monitoring. Set MONITORED_PEERS or MONITOR_ALL_PEERS=true")
            return {'interface': True, 'peers': {}}
        
        current_time = datetime.now()
        logger.debug(f"Current time: {current_time}")
        
        peer_status = {}
        
        for i, peer in enumerate(peers):
            peer_name = peer.get('name', f'peer-{i}')
            
            # Only monitor peers in our watch list
            if peer_name not in peers_to_monitor:
                logger.debug(f"Skipping peer '{peer_name}' (not in monitor list)")
                continue
            
            latest_handshake = peer.get('latest_handshake')
            peer_status_field = peer.get('status', 'unknown')
            
            logger.debug(f"Analyzing peer '{peer_name}': handshake='{latest_handshake}', status='{peer_status_field}'")
            
            # Check peer status - this API uses different logic than expected
            is_connected = False
            
            if latest_handshake and latest_handshake != 'No Handshake':
                try:
                    # Handle different handshake formats
                    if ':' in latest_handshake and latest_handshake.count(':') >= 2:
                        # Format: "0:00:26" (hours:minutes:seconds ago)
                        time_parts = latest_handshake.split(':')
                        if len(time_parts) == 3:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1])
                            seconds = int(time_parts[2])
                            time_since_handshake = hours * 3600 + minutes * 60 + seconds
                            
                            is_connected = time_since_handshake < self.config['handshake_timeout']
                            logger.debug(f"Peer '{peer_name}': handshake {time_since_handshake}s ago -> {'connected' if is_connected else 'disconnected'}")
                        else:
                            logger.debug(f"Peer '{peer_name}': Unexpected handshake format: '{latest_handshake}'")
                            is_connected = False
                    elif latest_handshake.replace('Z', '').replace('T', ' ').replace('-', '').replace(':', '').isdigit():
                        # ISO format: "2025-01-15T14:25:00Z"
                        handshake_time = datetime.fromisoformat(latest_handshake.replace('Z', '+00:00'))
                        time_since_handshake = (current_time - handshake_time).total_seconds()
                        is_connected = time_since_handshake < self.config['handshake_timeout']
                        logger.debug(f"Peer '{peer_name}': handshake {time_since_handshake:.1f}s ago -> {'connected' if is_connected else 'disconnected'}")
                    else:
                        # Handle other handshake formats
                        logger.debug(f"Peer '{peer_name}': Non-standard handshake format: '{latest_handshake}'")
                        is_connected = False
                        
                except (ValueError, TypeError) as e:
                    logger.debug(f"Failed to parse handshake time for peer {peer_name}: {e}")
                    is_connected = False
            else:
                logger.debug(f"Peer '{peer_name}': No handshake data")
                is_connected = False
            
            # Also check the status field as fallback/confirmation
            if peer_status_field in ['running', 'connected', 'active']:
                if not is_connected:
                    logger.debug(f"Peer '{peer_name}': Status field '{peer_status_field}' overrides handshake analysis")
                is_connected = True
            elif peer_status_field in ['stopped', 'disconnected', 'inactive']:
                if is_connected:
                    logger.debug(f"Peer '{peer_name}': Status field '{peer_status_field}' overrides handshake analysis")
                is_connected = False
            
            peer_status[peer_name] = is_connected
            
            if not is_connected:
                logger.warning(f"Monitored peer '{peer_name}' is disconnected (handshake: {latest_handshake}, status: {peer_status_field})")
            else:
                logger.info(f"Monitored peer '{peer_name}' is connected")
        
        result = {'interface': True, 'peers': peer_status}
        logger.debug(f"Connection analysis result: {result}")
        return result
    
    def check_status_changes(self, current_status: Dict):
        """Check for status changes and send notifications."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check interface status
        if not current_status.get('interface', False):
            if self.last_status.get('interface', True):  # Was up, now down
                subject = f"WireGuard Interface Down - {self.config['config_name']}"
                body = f"""
WireGuard interface {self.config['config_name']} is DOWN.

Time: {timestamp}
Status: Interface not running

Please check the WireGuard service immediately.
"""
                self.email_notifier.send_notification(subject, body)
        else:
            # Interface is up, check peers
            peers = current_status.get('peers', {})
            last_peers = self.last_status.get('peers', {})
            
            disconnected_peers = []
            reconnected_peers = []
            
            for peer_name, is_connected in peers.items():
                was_connected = last_peers.get(peer_name, True)
                
                if not is_connected and was_connected:
                    disconnected_peers.append(peer_name)
                elif is_connected and not was_connected:
                    reconnected_peers.append(peer_name)
            
            # Send notifications for disconnections
            if disconnected_peers:
                subject = f"WireGuard Peer(s) Disconnected - {self.config['config_name']}"
                body = f"""
WireGuard peer(s) have disconnected from {self.config['config_name']}.

Time: {timestamp}
Disconnected peers: {', '.join(disconnected_peers)}

Current peer status:
"""
                for peer_name, is_connected in peers.items():
                    status = "Connected" if is_connected else "Disconnected"
                    body += f"  - {peer_name}: {status}\n"
                
                self.email_notifier.send_notification(subject, body)
            
            # Send notifications for reconnections
            if reconnected_peers:
                subject = f"WireGuard Peer(s) Reconnected - {self.config['config_name']}"
                body = f"""
WireGuard peer(s) have reconnected to {self.config['config_name']}.

Time: {timestamp}
Reconnected peers: {', '.join(reconnected_peers)}

Current peer status:
"""
                for peer_name, is_connected in peers.items():
                    status = "Connected" if is_connected else "Disconnected"
                    body += f"  - {peer_name}: {status}\n"
                
                self.email_notifier.send_notification(subject, body)
        
        self.last_status = current_status.copy()
    
    def test_api_connectivity(self):
        """Test API connectivity and display results."""
        logger.info("Testing API connectivity...")
        
        data = self.get_wireguard_status()
        if data is None:
            logger.error("API connectivity test failed")
            return False
        
        logger.info("API connectivity test successful")
        
        # Show interface info
        if 'data' in data and 'configurationInfo' in data['data']:
            config_info = data['data']['configurationInfo']
            logger.info(f"Interface '{config_info.get('Name')}' Status: {'UP' if config_info.get('Status') else 'DOWN'}")
            logger.info(f"Connected Peers: {config_info.get('ConnectedPeers', 0)}/{config_info.get('TotalPeers', 0)}")
        
        # Show all available peers
        if 'data' in data and 'configurationPeers' in data['data']:
            peers = data['data']['configurationPeers']
            logger.info(f"Total peers found: {len(peers)}")
            
            for i, peer in enumerate(peers):
                peer_name = peer.get('name', f'peer-{i}')
                handshake = peer.get('latest_handshake', 'Unknown')
                status = peer.get('status', 'unknown')
                logger.info(f"  - {peer_name}: handshake='{handshake}', status='{status}'")
        
        # Test monitoring logic
        status = self.analyze_connections(data)
        
        if status.get('interface'):
            peers = status.get('peers', {})
            if peers:
                monitored_count = len(peers)
                connected_count = sum(1 for connected in peers.values() if connected)
                logger.info(f"Monitoring {monitored_count} peers: {connected_count} connected, {monitored_count - connected_count} disconnected")
                
                for peer_name, is_connected in peers.items():
                    status_str = "Connected" if is_connected else "Disconnected"
                    logger.info(f"  - {peer_name}: {status_str}")
            else:
                logger.warning("No peers configured for monitoring")
                logger.info("Available peer names:")
                if 'data' in data and 'configurationPeers' in data['data']:
                    for peer in data['data']['configurationPeers']:
                        logger.info(f"  - '{peer.get('name', 'unnamed')}'")
                logger.info("Configure MONITORED_PEERS in .env or set MONITOR_ALL_PEERS=true")
        else:
            logger.warning("Interface is DOWN")
        
        return True
    
    def run_monitor(self, check_once=False):
        """Main monitoring loop."""
        logger.info("Starting WireGuard connection monitor...")
        logger.info(f"Monitoring configuration: {self.config['config_name']}")
        logger.info(f"Check interval: {self.config['check_interval']} seconds")
        
        if check_once:
            logger.info("Single check mode enabled")
        
        iteration = 0
        while True:
            iteration += 1
            logger.debug(f"Starting monitoring iteration {iteration}")
            
            try:
                # Get current status
                api_data = self.get_wireguard_status()
                
                if api_data is None:
                    self.consecutive_failures += 1
                    logger.error(f"Failed to get WireGuard status (consecutive failures: {self.consecutive_failures})")
                    
                    # Send alert after multiple consecutive failures
                    if self.consecutive_failures >= 3:
                        subject = f"WireGuard Monitoring Alert - API Unavailable"
                        body = f"""
Unable to monitor WireGuard connections due to API failures.

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Consecutive failures: {self.consecutive_failures}
Configuration: {self.config['config_name']}

Please check:
1. WireGuard Dashboard API is running
2. API key is valid
3. Network connectivity

Monitoring will continue automatically.
"""
                        self.email_notifier.send_notification(subject, body)
                        self.consecutive_failures = 0  # Reset to avoid spam
                else:
                    self.consecutive_failures = 0
                    current_status = self.analyze_connections(api_data)
                    self.check_status_changes(current_status)
                    
                    # Log current status
                    if current_status.get('interface'):
                        peers = current_status.get('peers', {})
                        if isinstance(peers, dict):
                            connected_count = sum(1 for connected in peers.values() if connected)
                            total_peers = len(peers)
                            logger.info(f"Status check: Interface UP, Peers: {connected_count}/{total_peers} connected")
                        else:
                            logger.info("Status check: Interface UP, no peer data")
                    else:
                        logger.warning("Status check: Interface DOWN")
                
                if check_once:
                    logger.info("Single check completed, exiting")
                    break
                
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitoring loop: {e}")
                logger.debug(f"Exception details: {type(e).__name__}: {str(e)}", exc_info=True)
            
            if not check_once:
                # Wait for next check
                logger.debug(f"Waiting {self.config['check_interval']} seconds for next check...")
                time.sleep(self.config['check_interval'])

def validate_config():
    """Validate required configuration settings."""
    required_settings = {
        'WG_API_KEY': 'WireGuard API key',
        'SMTP_USERNAME': 'SMTP username',
        'SMTP_PASSWORD': 'SMTP password',
        'FROM_EMAIL': 'From email address',
    }
    
    missing = []
    for env_var, description in required_settings.items():
        if not os.getenv(env_var):
            missing.append(f"{env_var} ({description})")
    
    if missing:
        logger.error("Missing required environment variables:")
        for item in missing:
            logger.error(f"  - {item}")
        logger.error("Please check your .env file and ensure all required variables are set.")
        return False
    
    return True

def main():
    """Main entry point."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Setup logging based on arguments
    global logger
    logger = setup_logging(verbose=args.verbose, debug=args.debug)
    
    print("WireGuard Connection Monitor")
    print("=" * 40)
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        logger.error(".env file not found!")
        logger.error("Please copy .env.example to .env and configure your settings.")
        return
    
    # Validate configuration
    if not validate_config():
        return
    
    logger.info(f"Configuration loaded successfully")
    logger.info(f"Monitoring WireGuard config: {CONFIG['config_name']}")
    logger.info(f"API URL: {CONFIG['api_url']}")
    logger.info(f"Email notifications will be sent to: {', '.join(CONFIG['to_emails'])}")
    
    if args.debug:
        logger.info("Debug mode enabled - detailed logging active")
    elif args.verbose:
        logger.info("Verbose mode enabled")
    
    # Create email notifier instance
    email_config = {
        'smtp_server': CONFIG['smtp_server'],
        'smtp_port': CONFIG['smtp_port'],
        'smtp_username': CONFIG['smtp_username'],
        'smtp_password': CONFIG['smtp_password'],
        'from_email': CONFIG['from_email'],
        'to_emails': CONFIG['to_emails']
    }
    email_notifier = EmailNotifier(email_config)
    
    # Create monitor with email notifier
    monitor = WireGuardMonitor(CONFIG, email_notifier)
    
    try:
        if args.test_email:
            logger.info("Testing email configuration...")
            email_notifier.send_test_email(
                CONFIG['config_name'],
                CONFIG['api_url'],
                CONFIG['check_interval']
            )
            
        elif args.config_test:
            logger.info("Testing configuration and API connectivity...")
            if monitor.test_api_connectivity():
                logger.info("Configuration test completed successfully")
            else:
                logger.error("Configuration test failed")
                
        elif args.check_once:
            logger.info("Performing single status check...")
            monitor.run_monitor(check_once=True)
            
        else:
            # Normal monitoring mode
            monitor.run_monitor()
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.debug:
            logger.exception("Full traceback:")

if __name__ == "__main__":
    main()