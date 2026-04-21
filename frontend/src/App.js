import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Home = () => {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      try {
        const { data } = await axios.get(`${API}/bot/status`);
        if (mounted) setStatus(data);
      } catch (e) {
        if (mounted) setError(e.message);
      }
    };
    fetchStatus();
    const t = setInterval(fetchStatus, 5000);
    return () => {
      mounted = false;
      clearInterval(t);
    };
  }, []);

  const running = status?.bot_running;

  return (
    <div className="ts-root">
      <div className="ts-card" data-testid="bot-status-card">
        <div className="ts-badge" data-testid="bot-status-badge">
          <span className={`ts-dot ${running ? "on" : "off"}`} />
          {running ? "Bot online" : "Bot offline"}
        </div>

        <h1 className="ts-title">Tiger-SMS Discord Bot</h1>
        <p className="ts-sub">
          A Discord bot that buys virtual phone numbers from tiger-sms.com and
          posts the SMS code into the channel it was invoked from.
        </p>

        <div className="ts-grid">
          <div className="ts-chip" data-testid="chip-buy"><code>/buy</code> <span>purchase a number</span></div>
          <div className="ts-chip" data-testid="chip-status"><code>/status</code> <span>check an activation</span></div>
          <div className="ts-chip" data-testid="chip-cancel"><code>/cancel</code> <span>release a number</span></div>
          <div className="ts-chip" data-testid="chip-balance"><code>/balance</code> <span>tiger-sms balance</span></div>
          <div className="ts-chip" data-testid="chip-services"><code>/services</code> <span>popular service codes</span></div>
          <div className="ts-chip" data-testid="chip-countries"><code>/countries</code> <span>popular country IDs</span></div>
        </div>

        <div className="ts-orders" data-testid="recent-orders">
          <h2>Recent orders</h2>
          {!status && !error && <p className="ts-muted">Loading…</p>}
          {error && <p className="ts-err">Backend unreachable: {error}</p>}
          {status?.recent_orders?.length === 0 && (
            <p className="ts-muted">No orders yet. Run <code>/buy</code> in Discord.</p>
          )}
          {status?.recent_orders?.length > 0 && (
            <ul>
              {status.recent_orders.map((o) => (
                <li key={o.activation_id} data-testid={`order-${o.activation_id}`}>
                  <span className={`ts-pill ${o.status?.toLowerCase()}`}>{o.status}</span>
                  <code>+{o.phone}</code>
                  <span className="ts-meta">
                    {o.service} · {o.country} ·{" "}
                    {o.code ? <b>code: {o.code}</b> : <i>no code yet</i>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="ts-footer">
          Prefix commands (<code>!buy</code>, <code>!balance</code>…) also work.
        </p>
      </div>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
