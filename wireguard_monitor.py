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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def load_config() -> Dict:
    """Load configuration from environment variables."""
    
    # Parse email recipients (comma-separated)
    to_emails_str = os.getenv('TO_EMAILS', 'admin@example.com')
    to_emails = [email.strip() for email in to_emails_str.split(',')]
    
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
    }

# Load configuration
CONFIG = load_config()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wireguard_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class WireGuardMonitor:
    def __init__(self, config: Dict):
        self.config = config
        self.last_status = {}  # Track last known status to avoid spam
        self.consecutive_failures = 0
        
    def get_wireguard_status(self) -> Optional[Dict]:
        """Fetch WireGuard configuration info from API."""
        headers = {
            'wg-dashboard-apikey': self.config['api_key']
        }
        
        url = f"{self.config['api_url']}/getWireguardConfigurationInfo"
        params = {'configurationName': self.config['config_name']}
        
        for attempt in range(self.config['max_retries']):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=self.config['connection_timeout']
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"API returned status {response.status_code}: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"API request attempt {attempt + 1} failed: {e}")
                
                if attempt < self.config['max_retries'] - 1:
                    time.sleep(self.config['retry_delay'])
        
        return None
    
    def analyze_connections(self, data: Dict) -> Dict[str, bool]:
        """Analyze connection data and return status for each peer."""
        if not data or 'data' not in data:
            logger.error("Invalid API response format")
            return {}
        
        config_data = data['data']
        peer_status = {}
        
        # Check if the interface is up
        interface_status = config_data.get('status', 'down').lower() == 'up'
        
        if not interface_status:
            logger.warning(f"WireGuard interface {self.config['config_name']} is down")
            return {'interface': False}
        
        # Check peers
        peers = config_data.get('peers', [])
        if not peers:
            logger.warning("No peers found in configuration")
            return {'interface': True, 'peers': False}
        
        current_time = datetime.now()
        
        for peer in peers:
            peer_name = peer.get('name', peer.get('id', 'unknown'))
            latest_handshake = peer.get('latest_handshake')
            
            if latest_handshake and latest_handshake != 'N/A':
                try:
                    # Parse handshake time (adjust format as needed)
                    handshake_time = datetime.fromisoformat(latest_handshake.replace('Z', '+00:00'))
                    time_since_handshake = (current_time - handshake_time).total_seconds()
                    
                    # Consider connection alive if handshake within configured timeout
                    is_connected = time_since_handshake < self.config['handshake_timeout']
                    peer_status[peer_name] = is_connected
                    
                    if not is_connected:
                        logger.warning(f"Peer {peer_name} last handshake: {time_since_handshake:.0f}s ago")
                        
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse handshake time for peer {peer_name}: {e}")
                    peer_status[peer_name] = False
            else:
                logger.warning(f"Peer {peer_name} has no handshake data")
                peer_status[peer_name] = False
        
        return {'interface': True, 'peers': peer_status}
    
    def send_email_notification(self, subject: str, body: str):
        """Send email notification."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['from_email']
            msg['To'] = ', '.join(self.config['to_emails'])
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            server.starttls()
            server.login(self.config['smtp_username'], self.config['smtp_password'])
            
            for to_email in self.config['to_emails']:
                server.sendmail(self.config['from_email'], to_email, msg.as_string())
            
            server.quit()
            logger.info(f"Email notification sent: {subject}")
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
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
                self.send_email_notification(subject, body)
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
                
                self.send_email_notification(subject, body)
            
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
                
                self.send_email_notification(subject, body)
        
        self.last_status = current_status.copy()
    
    def run_monitor(self):
        """Main monitoring loop."""
        logger.info("Starting WireGuard connection monitor...")
        logger.info(f"Monitoring configuration: {self.config['config_name']}")
        logger.info(f"Check interval: {self.config['check_interval']} seconds")
        
        while True:
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
                        self.send_email_notification(subject, body)
                        self.consecutive_failures = 0  # Reset to avoid spam
                else:
                    self.consecutive_failures = 0
                    current_status = self.analyze_connections(api_data)
                    self.check_status_changes(current_status)
                    
                    # Log current status
                    if current_status.get('interface'):
                        peers = current_status.get('peers', {})
                        connected_count = sum(1 for connected in peers.values() if connected)
                        total_peers = len(peers)
                        logger.info(f"Status check: Interface UP, Peers: {connected_count}/{total_peers} connected")
                    else:
                        logger.warning("Status check: Interface DOWN")
                
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitoring loop: {e}")
            
            # Wait for next check
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
    
    monitor = WireGuardMonitor(CONFIG)
    monitor.run_monitor()

if __name__ == "__main__":
    main()