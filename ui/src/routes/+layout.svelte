<script lang="ts">
  import { page } from "$app/stores";
  export let data;

  const navItems = [
    { href: "/", label: "Dashboard" },
    { href: "/pipeline", label: "Pipeline" },
    { href: "/approvals", label: "Approvals" },
    { href: "/agents", label: "Agents" },
    { href: "/policies", label: "Policies" }
  ];
</script>

<main class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo-dot"></div>
      <div class="logo-text">
        <div class="logo-title">AI Governance</div>
        <div class="logo-subtitle">Demo console</div>
      </div>
    </div>

    <nav class="nav">
      {#each navItems as item}
        <a
          href={item.href}
          class:nav-item-active={$page.url.pathname === item.href}
          class="nav-item"
        >
          {item.label}
        </a>
      {/each}
    </nav>

    <div class="sidebar-footer">
      <div class="env-pill">Local · localhost:8000</div>
      <div class="sidebar-note">
        Registry &amp; risk engine
      </div>
    </div>
  </aside>

  <section class="main">
    <header class="topbar">
      <div class="topbar-title">
        <h1>AI Governance Demo</h1>
        <p>See · Score · Safeguard · Watch</p>
      </div>
      <div class="topbar-right">
        <span class="badge badge-green">Demo environment</span>
      </div>
    </header>

    <div class="page">
      <slot />
    </div>
  </section>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
      sans-serif;
    background: #020617;
    color: #e5e7eb;
  }

  .app-shell {
    display: grid;
    grid-template-columns: 260px 1fr;
    min-height: 100vh;
    background: radial-gradient(circle at top left, #1e293b 0, #020617 55%);
  }

  .sidebar {
    border-right: 1px solid #111827;
    padding: 18px 16px;
    background: rgba(2, 6, 23, 0.98);
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .sidebar-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-bottom: 10px;
    border-bottom: 1px solid #111827;
  }

  .logo-dot {
    width: 20px;
    height: 20px;
    border-radius: 999px;
    background: conic-gradient(from 180deg, #22c55e, #06b6d4, #6366f1, #22c55e);
    box-shadow: 0 0 18px rgba(34, 197, 94, 0.6);
  }

  .logo-text {
    display: flex;
    flex-direction: column;
  }

  .logo-title {
    font-weight: 600;
    font-size: 15px;
  }

  .logo-subtitle {
    font-size: 11px;
    color: #9ca3af;
  }

  .nav {
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .nav-item {
    padding: 7px 10px;
    border-radius: 8px;
    font-size: 13px;
    color: #9ca3af;
    text-decoration: none;
    display: block;
    transition: background 0.1s ease, color 0.1s ease, transform 0.05s ease;
  }

  .nav-item:hover {
    background: #020617;
    color: #e5e7eb;
    transform: translateX(1px);
  }

  .nav-item-active {
    background: linear-gradient(90deg, #22c55e11, #22c55e22);
    color: #f9fafb;
    border: 1px solid #22c55e55;
  }

  .sidebar-footer {
    margin-top: auto;
    padding-top: 12px;
    border-top: 1px solid #111827;
    font-size: 11px;
    color: #9ca3af;
  }

  .env-pill {
    display: inline-flex;
    padding: 3px 8px;
    border-radius: 999px;
    border: 1px solid #1f2937;
    background: #020617;
    font-size: 10px;
  }

  .sidebar-note {
    margin-top: 6px;
  }

  .main {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 22px;
    border-bottom: 1px solid #111827;
    backdrop-filter: blur(10px);
    background: linear-gradient(
      90deg,
      rgba(15, 23, 42, 0.96),
      rgba(2, 6, 23, 0.96)
    );
  }

  .topbar-title h1 {
    margin: 0;
    font-size: 18px;
  }

  .topbar-title p {
    margin: 2px 0 0;
    font-size: 12px;
    color: #9ca3af;
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .badge {
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 999px;
    border: 1px solid #1f2937;
  }

  .badge-green {
    background: #064e3b;
    border-color: #059669;
    color: #bbf7d0;
  }

  .page {
    padding: 18px 22px 28px;
  }

  @media (max-width: 800px) {
    .app-shell {
      grid-template-columns: 1fr;
    }
    .sidebar {
      display: none;
    }
  }
</style>
