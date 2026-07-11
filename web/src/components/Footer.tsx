/**
 * Footer — site-wide footer.
 * Contains: GitHub link, MIT license mention, built-with credit.
 */
export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer
      style={{
        borderTop: "1px solid var(--border)",
        backgroundColor: "var(--surface)",
      }}
      className="mt-auto"
    >
      <div
        className="max-w-6xl mx-auto px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-3"
      >
        {/* Left — copyright + license */}
        <p
          style={{
            fontFamily: "var(--font-mono)",
            color: "var(--text-dim)",
            fontSize: "0.8125rem",
          }}
        >
          © {year} PyScripts — MIT License
        </p>

        {/* Right — links */}
        <div className="flex items-center gap-5">
          <a
            href="https://github.com/WantedChip/python-scripts"
            target="_blank"
            rel="noopener noreferrer"
            id="footer-github-link"
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--text-muted)",
              fontSize: "0.8125rem",
              transition: "color 0.15s ease",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.375rem",
            }}
            className="hover:text-white"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M12 0C5.373 0 0 5.373 0 12c0 5.303 3.438 9.8 8.205 11.387.6.113.82-.26.82-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.757-1.333-1.757-1.089-.744.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.51 11.51 0 0112 5.803a11.51 11.51 0 013.002.404c2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.218.694.825.576C20.565 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
            </svg>
            View on GitHub
          </a>

          <span
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--text-dim)",
              fontSize: "0.8125rem",
            }}
          >
            Built with{" "}
            <a
              href="https://nextjs.org"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--text-muted)", transition: "color 0.15s ease" }}
              className="hover:text-white"
            >
              Next.js
            </a>
          </span>
        </div>
      </div>
    </footer>
  );
}
