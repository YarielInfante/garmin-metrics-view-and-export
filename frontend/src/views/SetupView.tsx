import { FormEvent, useState } from "react";
import { postJson } from "../api";

export function SetupView() {
  const [step, setStep] = useState<"login" | "mfa" | "done">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await postJson<{ status: string }>("/api/auth/login", { email, password });
      setStep(r.status === "needs_mfa" ? "mfa" : "done");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await postJson("/api/auth/mfa", { code });
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  const input =
    "data w-full border border-carbon-500 bg-carbon-800 px-3 py-2 text-sm text-bone-50 outline-none focus:border-signal";

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="panel rise w-full max-w-md p-8">
        <div className="mb-1 label text-sm text-signal">Garmin Training Analytics</div>
        <h1 className="mb-5 font-label text-2xl uppercase tracking-wide text-bone-50">
          Connect your Garmin account
        </h1>

        {step === "done" ? (
          <div>
            <p className="data text-sm text-easy">Connected — loading your dashboard…</p>
            <p className="data mt-2 text-xs text-bone-300">
              Your first sync is running in the background; the dashboard will fill in as it lands.
            </p>
          </div>
        ) : step === "mfa" ? (
          <form onSubmit={verify}>
            <p className="data mb-4 text-sm text-bone-300">
              Enter the multi-factor code Garmin just sent you.
            </p>
            <label className="label mb-1.5 block text-[11px] text-bone-300">MFA code</label>
            <input
              autoFocus
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className={input}
              placeholder="000000"
            />
            {error && <p className="data mt-3 text-xs text-hard">{error}</p>}
            <button
              type="submit"
              disabled={busy || !code}
              className="label mt-5 w-full border border-signal bg-signal/10 px-4 py-2.5 text-sm text-signal transition-colors hover:bg-signal/20 disabled:opacity-40"
            >
              {busy ? "Verifying…" : "Verify code"}
            </button>
            <button
              type="button"
              onClick={() => {
                setStep("login");
                setError(null);
                setCode("");
              }}
              className="data mt-3 w-full text-center text-xs text-bone-300 hover:text-bone-100"
            >
              ← start over
            </button>
          </form>
        ) : (
          <form onSubmit={login}>
            <label className="label mb-1.5 block text-[11px] text-bone-300">Garmin email</label>
            <input
              autoFocus
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={input}
              placeholder="you@example.com"
            />
            <label className="label mb-1.5 mt-4 block text-[11px] text-bone-300">Password</label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={input}
              placeholder="••••••••"
            />
            {error && <p className="data mt-3 text-xs text-hard">{error}</p>}
            <button
              type="submit"
              disabled={busy || !email || !password}
              className="label mt-5 w-full border border-signal bg-signal/10 px-4 py-2.5 text-sm text-signal transition-colors hover:bg-signal/20 disabled:opacity-40"
            >
              {busy ? "Signing in… (this can take a minute)" : "Sign in"}
            </button>
          </form>
        )}

        <p className="data mt-6 border-t border-carbon-700 pt-4 text-[11px] leading-relaxed text-carbon-500">
          Your password is used once to obtain a Garmin access token and is <span className="text-bone-300">never stored</span>.
          Only the token is saved, locally on this machine. Nothing is sent anywhere but Garmin, and only from your own computer.
        </p>
      </div>
    </div>
  );
}
