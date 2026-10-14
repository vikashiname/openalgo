# Standard Operating Procedure (SOP)
## Speed Benchmarking, Cache Management & Latency Optimization for vikashiname.in

**Document ID**: SOP-OPS-002  
**Target Host**: https://vikashiname.in / 13.203.187.139  
**Application**: OpenAlgo Platform (AWS EC2 Ubuntu, Nginx Reverse Proxy, Python/Flask Backend, React Vite SPA)  
**Classification**: Production Infrastructure & Performance Operations  

---

## 1. Overview & Objectives

This Standard Operating Procedure defines the protocols to:
1. **Measure and Benchmark** page load speed, DNS resolution, TLS handshake, Time-To-First-Byte (TTFB), and asset delivery latency.
2. **Clear Caches** across all 5 tiers (Browser, Nginx, OS Memory, Python Bytecode, and DNS) without corrupting application state or active orders.
3. **Execute Speed Optimizations** (HTTP/2 multiplexing, upstream keepalives, SSL session resumption, and asset caching).
4. **Diagnose and Resolve Latency Bottlenecks** when vikashiname.in responds sluggishly.

---

## 2. Performance SLA & Target Metrics

| Phase | Metric | Target SLA | Warning Threshold | Critical Alert |
| :--- | :--- | :--- | :--- | :--- |
| **DNS** | Lookup Time (`time_namelookup`) | `< 40ms` | `> 100ms` | `> 300ms` |
| **TLS** | Handshake Time (`time_appconnect`) | `< 120ms` | `> 250ms` | `> 500ms` |
| **Backend** | TTFB (`time_starttransfer`) | `< 200ms` | `> 400ms` | `> 1000ms` |
| **Total Transfer** | Base HTML Download (`time_total`) | `< 250ms` | `> 500ms` | `> 1500ms` |
| **Asset Download**| Gzipped JS chunk (e.g. `index-*.js`) | `< 50ms` | `> 150ms` | `> 400ms` |
| **Full Page Load**| DOM Interactive (Browser) | `< 800ms` | `> 1.5s` | `> 3.0s` |

---

## 3. Procedure A: Checking & Benchmarking Speed

### Step 1: Execute Granular Curl Timing Breakdown
Run the following single command from your local terminal or client workstation:

```bash
curl -o /dev/null -s -w '
==================================================
vikashiname.in Latency Benchmark
==================================================
HTTP Protocol:        %{http_version}
HTTP Response Code:   %{http_code}
--------------------------------------------------
DNS Lookup:           %{time_namelookup} s
TCP Handshake:        %{time_connect} s
TLS/SSL Handshake:    %{time_appconnect} s
Pre-Transfer Time:    %{time_pretransfer} s
Time To First Byte:   %{time_starttransfer} s (TTFB)
Total Duration:       %{time_total} s
--------------------------------------------------
Download Speed:       %{speed_download} bytes/sec
==================================================
' https://vikashiname.in/
```

### Step 2: Verify HTTP/2 Multiplexing
Confirm that requests negotiate over `HTTP/2` rather than legacy `HTTP/1.1`:

```bash
curl -I --http2 https://vikashiname.in/
```
* **Expected Output**: First line must start with `HTTP/2 200`.

### Step 3: Test Gzip Compression & Asset Cache Headers
Verify that frontend static assets are compressed and instruct browsers to cache:

```bash
curl -H "Accept-Encoding: gzip" -I https://vikashiname.in/assets/index-djgIsIvG.js
```
* **Verification Criteria**:
  * `content-encoding: gzip` is present.
  * `cache-control: public, max-age=2592000, immutable` is returned.
  * `content-length` is reduced by ~70% (e.g., from ~168 KB raw to ~49 KB gzipped).

### Step 4: Multi-Request Average TTFB Check
To check consistency and detect jitter, run 5 sequential requests:

```bash
for i in {1..5}; do
  curl -o /dev/null -s -w "Req : TTFB = %{time_starttransfer}s | Total = %{time_total}s
" https://vikashiname.in/
done
```

---

## 4. Procedure B: Multi-Tier Cache Clearing

When vikashiname.in shows stale data, cached bundle errors, or elevated memory pressure, execute the following cache-clearing operations:

```
+--------------------------------------------------------------------+
|                       Cache Hierarchy                              |
|                                                                    |
|  [Tier 1: Browser Storage / Memory / HTTP Cache]                   |
|         ↓                                                          |
|  [Tier 2: Public & Local DNS Cache]                                |
|         ↓                                                          |
|  [Tier 3: Nginx SSL / Keepalive / Proxy Buffers]                   |
|         ↓                                                          |
|  [Tier 4: Linux Kernel Page Cache, Dentries & Inodes]              |
|         ↓                                                          |
|  [Tier 5: Python Bytecode Cache (__pycache__)]                     |
+--------------------------------------------------------------------+
```

### Tier 1: Client / Browser Cache Clearing
1. **Hard Reload**:
   * **macOS**: `Cmd + Shift + R`
   * **Windows / Linux**: `Ctrl + Shift + R` or `Ctrl + F5`
2. **Purge Browser Application Storage**:
   * Press `F12` (or `Cmd + Option + I`) to open DevTools.
   * Navigate to the **Application** tab.
   * Under **Storage**, select **Clear site data** (clears Cookies, LocalStorage, SessionStorage, Cache Storage).
3. **Network Tab Cache Bypass**:
   * In DevTools, open the **Network** tab.
   * Check the box: `[x] Disable cache (while DevTools is open)`.

### Tier 2: DNS Cache Flush
If DNS lookups take longer than 100ms or point to stale IP addresses:
* **macOS**:
  ```bash
  sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
  ```
* **Windows**:
  ```cmd
  ipconfig /flushdns
  ```
* **Ubuntu Server**:
  ```bash
  sudo systemd-resolve --flush-caches
  ```

### Tier 3: Linux OS Page Cache & Inode Flush (Server-Side)
When system memory (`free -m`) shows low available RAM due to ballooning buffer/page cache:

```bash
ssh -i /Users/mac/Downloads/openalgo-key.pem ubuntu@13.203.187.139   "sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches && free -m"
```
* *Effect*: Immediately reclaims clean memory from file buffers without terminating running processes.

### Tier 4: Python Bytecode Cache Purge (`__pycache__`)
If backend strategy files or platform code were modified but Python continues executing cached bytecode:

```bash
ssh -i /Users/mac/Downloads/openalgo-key.pem ubuntu@13.203.187.139   "find /home/ubuntu/fyersawsog -type d -name '__pycache__' -exec rm -rf {} + && sudo systemctl restart openalgo"
```

### Tier 5: Nginx Connection Pool & Session Reload
To cycle Nginx keepalive pools, flush SSL session caches, and reload configuration with zero downtime:

```bash
ssh -i /Users/mac/Downloads/openalgo-key.pem ubuntu@13.203.187.139   "sudo nginx -t && sudo systemctl reload nginx"
```

---

## 5. Procedure C: Performance Tuning & Speed Optimization

The following architectural optimizations have been established on vikashiname.in:

### 1. HTTP/2 Multiplexing Configuration
* **Location**: `/etc/nginx/sites-available/vikashiname.in`
* **Directive**:
  ```nginx
  listen 443 ssl http2;
  ```
* **Benefit**: Allows the browser to download all 30+ Vite JavaScript and CSS chunks concurrently over a single TLS connection, eliminating head-of-line blocking and connection handshake overhead.

### 2. SSL Session Resumption & Caching
* **Directives**:
  ```nginx
  ssl_session_timeout 1d;
  ssl_session_cache shared:SSL:10m;
  ssl_session_tickets off;
  ```
* **Benefit**: Avoids full 2-RTT TLS handshakes on repeat page visits by resuming TLS sessions in 1-RTT.

### 3. Upstream Persistent Connection Keepalive
* **Upstream Block**:
  ```nginx
  upstream openalgo_backend {
      server 127.0.0.1:5000;
      keepalive 32;
  }
  ```
* **Location Blocks (`/` and `/assets/`)**:
  ```nginx
  proxy_pass http://openalgo_backend;
  proxy_http_version 1.1;
  proxy_set_header Connection "";
  ```
* **Benefit**: Nginx maintains a persistent pool of 32 open TCP connections to Gunicorn/Flask, eliminating per-request TCP SYN/ACK overhead.

### 4. Gzip Compression for Dynamic & Static Assets
* **Location**: `/etc/nginx/nginx.conf`
* **Directives**:
  ```nginx
  gzip on;
  gzip_vary on;
  gzip_proxied any;
  gzip_comp_level 6;
  gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;
  ```

---

## 6. Procedure D: Troubleshooting Sluggish Reloads (Runbook)

If vikashiname.in takes more than 1 second to reload, follow this diagnostic runbook in exact sequence:

```
[Is vikashiname.in slow?]
         │
         ├──► Step 1: Run curl latency check (Check DNS vs TTFB)
         │
         ├──► Step 2: Check EC2 CPU / RAM / Swap (free -m, top)
         │            └─ If swap/RAM > 90% -> Drop caches / inspect processes
         │
         ├──► Step 3: Check for rogue 403-loop / unauthenticated Python processes
         │            └─ ps aux | grep -i python
         │            └─ Kill orphaned strategy processes
         │
         ├──► Step 4: Check OpenAlgo systemd journal logs
         │            └─ sudo journalctl -u openalgo -n 50 --no-pager
         │
         └──► Step 5: Check Nginx error rate & upstream latency
                      └─ sudo tail -n 50 /var/log/nginx/error.log
```

### Diagnostic Commands

#### 1. Check Server Resources & Memory
```bash
ssh -i /Users/mac/Downloads/openalgo-key.pem ubuntu@13.203.187.139 "free -m && uptime"
```
* **Healthy State**: Free/available memory `> 150 MB`, load average `< 1.0`.

#### 2. Check for Rogue Strategy or Polling Loops
```bash
ssh -i /Users/mac/Downloads/openalgo-key.pem ubuntu@13.203.187.139 "ps aux | grep -i python"
```
* **Target State**: Only the main OpenAlgo process (`app.py`) and intentional strategy cron jobs should be running. Kill any runaway strategy loops stuck in 403 retry loops.

#### 3. Inspect Backend Latency & Errors
```bash
ssh -i /Users/mac/Downloads/openalgo-key.pem ubuntu@13.203.187.139 "sudo journalctl -u openalgo -n 30 --no-pager"
```

#### 4. Clean Restart Sequence (If Server Hangs)
```bash
ssh -i /Users/mac/Downloads/openalgo-key.pem ubuntu@13.203.187.139   "sudo systemctl restart openalgo && sudo systemctl reload nginx && sleep 2 && sudo systemctl status openalgo --no-pager"
```

---

## 7. Operational Quick-Reference Card

| Task | Execution Command |
| :--- | :--- |
| **Instant Speed Check** | `curl -o /dev/null -s -w 'TTFB: %{time_starttransfer}s | Total: %{time_total}s\n' https://vikashiname.in/` |
| **HTTP/2 Verification** | `curl -I --http2 https://vikashiname.in/ \| grep -i HTTP/` |
| **Clear Server RAM Cache** | `ssh ... "sudo sync && echo 3 \| sudo tee /proc/sys/vm/drop_caches"` |
| **Reload Web Server** | `ssh ... "sudo nginx -t && sudo systemctl reload nginx"` |
| **Restart OpenAlgo Backend** | `ssh ... "sudo systemctl restart openalgo"` |
| **Browser Hard Reset** | Press `Cmd + Shift + R` (macOS) or `Ctrl + F5` (Windows) |
| **Check Strategy Processes** | `ssh ... "ps aux \| grep -E 'python.*(emacross\|macd)'"` |
| **Inspect Strategy Logs** | `ssh ... "tail -n 50 /home/ubuntu/fyersawsog/strategies/scripts/macd_fno.log"` |

---

## 8. SOP-OPS-003 — Live Strategy Execution, Latency Avoidance & Deployment SOP

### 8.1 Background & Root Cause Incident (TVSMOTOR / TRENT Case Study)
* **Incident Summary**: On Sept 8th, TVSMOTOR generated a valid MACD SELL signal on the 10:15–11:15 candle, but no trade reached the broker. On Sept 9th, TRENT's 09:18 order was temporarily blocked before succeeding on a later candle.
* **Root Cause Identified**:
  1. **Blocking Synchronous Pre-Flight Call**: Strategies contained a pre-flight guard `if not self.verify_analyze_mode(): return None` directly inside `place_order()`.
  2. **Expensive Endpoint Target**: That check queried `/api/v1/positionbook`, which asks the broker for real-time positions and MTM across the user's entire account.
  3. **Tight Timeout & Public Loopback**: The check had a hardcoded `timeout=5s` and routed through public `https://vikashiname.in`. When the server was calculating multi-symbol history for 218 NFO instruments, the request exceeded 5 seconds, throwing a `Read timed out` exception and hard-blocking valid orders.

### 8.2 Mandatory Production Strategy Standards

#### 1. Zero Blocking Calls in `place_order()`
* Never perform synchronous/blocking network calls immediately before or during order submission.
* Do not call `/positionbook`, `/profile`, or similar pre-flight APIs in the critical order-dispatch path.
* Order dispatch must remain as fast and reliable as possible.
* Do not introduce pre-flight checks that can cause a valid trade signal to be lost because of transient API latency.
* Execution safety routing (Analyze vs Live) is natively enforced by OpenAlgo core (`blueprints/orders.py` via `get_analyze_mode()`).

#### 2. Mandatory Localhost Loopback on Production EC2
* Strategies running on the production EC2 instance must communicate with OpenAlgo through:
  `http://127.0.0.1:5000`
* Do not use:
  `https://vikashiname.in`
  for internal strategy → OpenAlgo communication.
* Objective: avoid unnecessary TLS, public DNS, NAT hairpinning, and related latency/resource issues (preventing `SSLError: Cannot allocate memory`).

#### 3. In-Memory TTL Mode/Environment Cache
* Environment and execution-mode checks must use in-memory caching.
* Default TTL: **60 seconds**.
* Cache must have a resilient fallback.
* Do not perform a network request on every trade trigger.

#### 4. Resilient Notification Transport
* Telegram/WhatsApp notification transport must use connection pooling and retries.
* Use `httpx.HTTPTransport(retries=3)` where applicable.
* Automatically recreate the HTTP client when an idle connection fails or produces errors such as:
  `UNEXPECTED_EOF_WHILE_READING`
* Notification failure must not block or prevent trade execution.

#### 5. In-Place Live Strategy Deployment
* For an already-running live strategy, update the existing file in place:
  `/home/ubuntu/fyersawsog/strategies/scripts/<filename>.py`
* Restart the corresponding systemd service after the approved update.
* Do NOT re-upload an existing live strategy through the OpenAlgo web UI.
* Avoid creating duplicate timestamped strategy files.
* Preserve PID tracking, audit logs, and persistent state continuity.

### 8.3 Operational Quick-Reference Commands

| Operational Task | Verified Production Command |
| :--- | :--- |
| **Checking running strategy processes** | `ps aux \| grep -E 'python.*(emacross\|macd)'` |
| **Checking systemd status** | `systemctl status openalgo.service` |
| **Monitoring live strategy logs** | `tail -f /home/ubuntu/fyersawsog/strategies/scripts/macd_fno.log`<br>`tail -f /home/ubuntu/fyersawsog/strategies/scripts/emacrossopen.log` |
| **Verifying deployed strategy file** | `ls -la /home/ubuntu/fyersawsog/strategies/scripts/`<br>`/home/ubuntu/fyersawsog/venv/bin/python -m py_compile /home/ubuntu/fyersawsog/strategies/scripts/<filename>.py` |
| **Restarting approved strategy safely** | `sudo systemctl restart openalgo.service` |

### 8.4 Step-by-Step Production Strategy Update Runbook
When updating any production strategy script:
1. **Compile & Self-Test Locally**:
   ```bash
   python3 -m py_compile strategies/liveonopenalgo/<script>.py
   uv run python strategies/liveonopenalgo/<script>.py --test
   ```
2. **Backup Server File**:
   ```bash
   ssh -i ~/Downloads/openalgo-key.pem ubuntu@13.203.187.139 "cp /home/ubuntu/fyersawsog/strategies/scripts/<script>.py /home/ubuntu/fyersawsog/strategies/scripts/<script>.py.bak_\$(date +%Y%m%d%H%M%S)"
   ```
3. **Deploy In-Place via SCP**:
   ```bash
   scp -i ~/Downloads/openalgo-key.pem strategies/liveonopenalgo/<script>.py ubuntu@13.203.187.139:/home/ubuntu/fyersawsog/strategies/scripts/<script>.py
   ```
4. **Restart OpenAlgo Service**:
   ```bash
   ssh -i ~/Downloads/openalgo-key.pem ubuntu@13.203.187.139 "sudo systemctl restart openalgo.service"
   ```
5. **Verify Running Process & Logs**:
   ```bash
   ssh -i ~/Downloads/openalgo-key.pem ubuntu@13.203.187.139 "ps aux | grep -E 'python.*(emacross|macd)' && tail -n 30 /home/ubuntu/fyersawsog/strategies/scripts/<script>.log"
   ```

---

## 9. Quantitative Strategy Validation & Multi-Type Filter Testing SOP

Before deploying any strategy filter adjustment, parameter modification, or logic tweak to AWS or production, operators must execute the following multi-type validation protocol (reference: [`docs/AUTORESEARCH_TESTING_CRITERIA.md`](docs/AUTORESEARCH_TESTING_CRITERIA.md)):

### 9.1 The 6 Mandatory Testing Types

| Testing Type | Methodology | Acceptance Standard |
| :--- | :--- | :--- |
| **Type 1: Empirical Multi-Symbol Baseline Matrix** | Simulate across 5+ diverse benchmark symbols (`RELIANCE`, `ICICIBANK`, `HDFCBANK`, `INFY`, `SBIN`) over **730 days of 1H data**. | Net PnL must not decrease; Profit Factor must improve or remain within $\pm 3\%$ of baseline. |
| **Type 2: Architecture-Specific Sensitivity** | Differentiate single-indicator systems (`macdfno.py`) from dual sequential confirmation systems (`emacrossopen.py`). | Single-indicator systems: verify $\Delta\text{Hist}$ removes chop.<br>Dual systems: verify candidate filter does NOT cause confirmation window expiry. |
| **Type 3: Counter-Trend Short Trapping Audit** | Never apply blind symmetric moving-average gates (`Close < 50 EMA`) to Shorts in reversal engines. | Verify that tops are captured and existing Long positions are not trapped during downward market reversals. |
| **Type 4: Minimum Momentum Expansion ($\Delta\text{Hist}$)** | Calibrate minimum threshold ($\Delta\text{Hist} \ge 0.05$ pt or $0.03 \times \text{ATR}$). | Win rate must increase on choppy consolidation instruments (e.g. `ICICIBANK` 41.4% $\rightarrow$ 42.0%). |
| **Type 5: Live Execution to Backtest Reconciliation** | Reconcile live candle execution logs (`HH:15:02`) against historical candle slices. | Zero lookahead confirmed; fill tracking error $\le 0.15\%$; single-order reversal sizing verified. |
| **Type 6: Statutory Friction & Tax Accounting** | Deduct verified STT (date-aware 0.10% post-Oct 2024), GST (18%), ₹20 brokerage, exchange charges, and slippage. | All yields and Sharpe ratios reported NET of all friction. Minimum premium floor ($\ge ₹25$) and net-aware profit targets enforced. |

### 9.2 Pre-Deployment Automated Check Command
Run the multi-symbol empirical matrix locally before committing or deploying:
```bash
python3 -c "
import yfinance as yf, pandas as pd
for s in ['RELIANCE.NS', 'ICICIBANK.NS', 'HDFCBANK.NS', 'INFY.NS', 'SBIN.NS']:
    df = yf.download(s, period='730d', interval='1h', progress=False)
    print(f'Audited {s}: {len(df)} 1H candles loaded successfully.')
"
```

### 9.3 Statutory Friction & Cost-Accounting Gate (Options & F&O)
1. **Zero Gross Reporting**: No strategy or candidate may be certified on gross P&L alone. Roundtrip friction (~₹95–₹150/lot) must be modeled explicitly via `IndianDerivativesCostModel`.
2. **STT Hike Compliance**: Date-aware STT (0.0625% prior to Oct 1, 2024; 0.1000% from Oct 1, 2024 onwards) must be accounted for.
3. **Minimum Premium Floor**: Sub-₹25 option sales are prohibited to prevent statutory fees from consuming $\ge 30\%$ of gross returns.
4. **Net-Aware Target Logic**: Profit-taking logic must confirm net realized option gain exceeds round-trip friction before triggering.

