# Deployment — Void Rig (Azure Ubuntu)

## Ports
| Service | Port |
|---|---|
| Manager API (FastAPI) | 8602 |
| Streamlit UI | 8603 |

## First-time server setup
```bash
# Copy setup script to server, then run:
bash setup_server.sh <OPENAI_API_KEY> <PINECONE_API_KEY>
```

## CI/CD — automatic on every push to `main`
GitHub Actions (`deploy.yml`) SSHs into Void Rig, pulls the latest code, reinstalls deps, and restarts both services.

Required GitHub Secrets (Settings → Secrets → Actions):
- `VOID_RIG_IP` — public IP of the server
- `VOID_RIG_USER` — `azureuser`
- `VOID_RIG_SSH_KEY` — private key content (the key Jaime shared)

## Manual commands on server
```bash
# Check service status
sudo systemctl status warframe-manager warframe-ui

# View live logs
sudo journalctl -fu warframe-manager
sudo journalctl -fu warframe-ui

# Restart manually
sudo systemctl restart warframe-manager warframe-ui

# Health check
curl http://localhost:8602/health
```
