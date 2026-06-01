# Oracle Cloud Free Tier Deployment Guide

Deploy **Restaurant Social Automation** on Oracle Cloud's **Always Free Tier** — a full ARM VM that runs 24/7, **free forever**.

## Prerequisites
- **Oracle Cloud account** at cloud.oracle.com (credit card needed for identity verification — **never charged**)
- **A domain (optional)** for HTTPS/SSL
- **SSH key pair** (generated during VM creation)

## Step 1: Create Your Free VM

1. Go to **cloud.oracle.com** → Sign in → **Create a VM instance**
2. Configure:
   - **Name**: `restaurant-automation`
   - **Image**: `Canonical Ubuntu 24.04` (Minimal is fine)
   - **Shape**: Click **Change shape** → **Ampere** tab → Select **VM.Standard.A1.Flex** with **1 OCPU** and **6 GB RAM**
   - **SSH Keys**: Upload your public key
3. Click **Create** (takes ~2-3 min)

## Step 2: Connect & Open Firewall

```bash
ssh -i /path/to/your-key ubuntu@<YOUR_VM_PUBLIC_IP>
```

In Oracle Cloud Console → Instance → VCN → Security Lists → **Add Ingress Rules**:

| Source | Protocol | Port | Description |
|--------|----------|------|-------------|
| 0.0.0.0/0 | TCP | 8000 | App API |
| 0.0.0.0/0 | TCP | 80 | HTTP (optional) |
| 0.0.0.0/0 | TCP | 443 | HTTPS (optional) |

## Step 3: Run the One-Click Setup

```bash
wget https://raw.githubusercontent.com/dinesh-choudhary123/Facebook-/main/deploy/oracle/setup.sh
chmod +x setup.sh
./setup.sh
```

This installs everything: Python, Tesseract, Nginx, clones the repo, sets up venv, creates systemd service (auto-start on boot).

## Step 4: Configure Environment

```bash
nano ~/restaurant-social-automation/.env
# Fill in your Facebook keys
sudo systemctl restart restaurant-social-automation
```

## Done! Your app is at:
```
http://<YOUR_VM_IP>:8000
```

## Managing the App

```bash
sudo systemctl status restaurant-social-automation
tail -f ~/restaurant-social-automation/logs/app.log
sudo systemctl restart restaurant-social-automation
```

## Domain + HTTPS (Optional)

Point your domain's DNS A record to the VM IP, then:

```bash
sudo certbot --nginx -d yourdomain.com
```

## Quick Links
- [Oracle Cloud Sign Up](https://signup.cloud.oracle.com)
- [Oracle Free Tier Docs](https://www.oracle.com/cloud/free/)
- [GitHub Repo](https://github.com/dinesh-choudhary123/Facebook-)
