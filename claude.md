# Claude.md - WireGuard Monitor Project

## Project Overview
This is a Python-based WireGuard connection monitoring system that tracks VPN peer connections via the WireGuard Dashboard API and sends email notifications when connections fail or recover. The project is designed for network engineers who need reliable monitoring of WireGuard VPN infrastructure.

## Project Structure
```
wireguard-monitor/
├── wireguard_monitor.py      # Main monitoring script (Python)
├── setup.sh                  # Automated installation script (Bash)
├── requirements.txt          # Python dependencies
├── .env.example             # Configuration template
├── .env                     # Actual configuration (created by user, git-ignored)
├── wireguard_monitor.log    # Runtime log file (created automatically)
├── README.md                # User documentation
├── LICENSE                  # MIT license
└── claude.md               # This file - AI assistant context
```

## Key Files and Their Purpose

### `wireguard_monitor.py` - Main Application
- **Language**: Python 3.6+
- **Purpose**: Core monitoring logic and email notification system
- **Key Functions**:
  - API polling of WireGuard Dashboard
  - Peer connection status analysis
  - Email alert generation
  - State tracking to prevent notification spam
  - Comprehensive logging and error handling

### `setup.sh` - Installation Script  
- **Language**: Bash
- **Purpose**: Automated deployment and service configuration
- **What it does**:
  - Creates Python virtual environment
  - Installs dependencies from requirements.txt
  - Creates systemd service configuration
  - Sets proper file permissions
  - Configures service for auto-start

### `.env` Configuration File
- **Purpose**: Environment variables for runtime configuration
- **Security**: Contains sensitive data (API keys, email credentials)
- **Status**: Must be created from .env.example, never committed to git

## Core Functionality

### Monitoring Logic
1. **API Integration**: Polls WireGuard Dashboard API endpoint
2. **Connection Analysis**: Checks peer handshake timestamps
3. **State Management**: Tracks connection status changes
4. **Notification System**: Sends email alerts on status changes

### Network Engineering Context
- **Protocol**: Monitors WireGuard VPN connections
- **API Endpoint**: `/api/getWireguardConfigurationInfo`
- **Handshake Timeout**: Default 5 minutes (300 seconds)
- **Monitoring Interval**: Configurable check frequency
- **Peer Identification**: By name rather than public key

## Configuration Variables

### Required Settings (.env file)
- `WG_API_KEY`: WireGuard Dashboard API authentication key
- `MONITORED_PEERS`: Comma-separated peer names to monitor
- `SMTP_USERNAME`: Email account for sending notifications  
- `SMTP_PASSWORD`: Email password (preferably app password)
- `FROM_EMAIL`: Sender email address

### Optional Settings (with defaults)
- `WG_API_URL`: API endpoint (default: http://localhost:10086/api)
- `WG_CONFIG_NAME`: WireGuard interface name (default: wg0)
- `CHECK_INTERVAL`: Polling frequency in seconds (default: 300)
- `HANDSHAKE_TIMEOUT`: Peer timeout threshold (default: 300)
- `SMTP_SERVER`: Mail server (default: smtp.gmail.com)
- `SMTP_PORT`: Mail server port (default: 587)

## Service Management

### SystemD Integration
- Service name: `wireguard-monitor`
- User: Non-root for security
- Auto-restart: Enabled with 10-second delay
- Logging: Via journalctl

### Common Commands
```bash
sudo systemctl start wireguard-monitor    # Start service
sudo systemctl stop wireguard-monitor     # Stop service  
sudo systemctl restart wireguard-monitor  # Restart service
sudo systemctl status wireguard-monitor   # Check status
sudo journalctl -u wireguard-monitor -f   # View live logs
```

## Dependencies (requirements.txt)
- Email handling libraries (smtplib - built-in)
- HTTP request libraries (likely requests)
- Configuration management (python-dotenv)
- JSON processing (json - built-in)
- Logging (logging - built-in)

## Code Architecture Notes

### For Python Beginners
- **Virtual Environment**: Uses venv for dependency isolation
- **Configuration**: Environment variables via .env file
- **Error Handling**: Try/catch blocks for API and email failures
- **Logging**: Both console and file output
- **State Management**: Tracks previous status to detect changes

### Network Engineering Focus
- **API Design**: RESTful interface to WireGuard Dashboard
- **Monitoring Strategy**: Handshake-based connection detection
- **Alert Logic**: Status change triggers (not continuous polling spam)
- **Timeout Configuration**: Customizable peer timeout thresholds
- **Multi-peer Support**: Can monitor multiple clients simultaneously

## Debugging and Troubleshooting

### Command Line Options
- `python3 wireguard_monitor.py -v`: Verbose output
- `python3 wireguard_monitor.py -d`: Debug mode
- `python3 wireguard_monitor.py --test-email`: Test email configuration
- `python3 wireguard_monitor.py --check-once`: Single status check

### Common Issues
1. **API Connection**: Verify WireGuard Dashboard is running and accessible
2. **Authentication**: Check API key validity and permissions
3. **Email Delivery**: Verify SMTP settings and app passwords
4. **Peer Names**: Ensure monitored peer names match dashboard configuration
5. **Permissions**: Service needs appropriate file access permissions

## Security Considerations
- API keys stored in environment variables
- Service runs as non-root user
- .env file has restrictive permissions (600)
- Email credentials use app passwords when possible
- systemd security restrictions applied

## Development Workflow
- **Local Testing**: Run directly with Python for development
- **Production Deployment**: Use systemd service via setup.sh
- **Configuration**: Always test with --test-email before deployment
- **Logging**: Monitor both application logs and systemd journal

## Integration Points
- **WireGuard Dashboard API**: Primary data source
- **SMTP Email System**: Notification delivery
- **SystemD**: Service management and logging
- **File System**: Configuration and log storage

## When to Modify This Project
- Adding new notification channels (Slack, Discord, etc.)
- Implementing additional monitoring metrics
- Customizing alert logic or thresholds  
- Adding database storage for historical data
- Implementing web dashboard for status viewing

## AI Assistant Guidance
When helping with this project:
1. **Configuration Questions**: Always verify .env settings first
2. **Python Issues**: Remember this is designed for beginners - explain concepts clearly
3. **Network Problems**: Consider WireGuard/networking knowledge level
4. **Service Issues**: Check both application logs and systemd status
5. **Security**: Always emphasize secure credential handling
6. **Testing**: Recommend using test flags before production deployment
