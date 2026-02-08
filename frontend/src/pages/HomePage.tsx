import { useState } from "react";
import { Link } from "react-router-dom";
import HelpModal from "../components/HelpModal";

export default function HomePage() {
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <div className="page home-page">
      <button className="help-btn" onClick={() => setHelpOpen(true)} aria-label="Help">?</button>
      <div className="home-hero">
        <div className="home-suits">♠ ♥ ♣ ♦</div>
        <h1>Poker Night</h1>
        <p className="home-sub">No-Limit Texas Hold'em</p>
      </div>
      <div className="button-group">
        <Link to="/create" className="btn btn-primary btn-lg">
          Create Game
        </Link>
        <Link to="/join" className="btn btn-secondary btn-lg">
          Join Game
        </Link>
      </div>
      <a
        href="https://github.com/jdstemmler/poker"
        target="_blank"
        rel="noopener noreferrer"
        className="github-link"
      >
        <svg
          viewBox="0 0 24 24"
          width="20"
          height="20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
        </svg>
        View on GitHub
      </a>
      <a
        href="https://buymeacoffee.com/jdstemmler"
        target="_blank"
        rel="noopener noreferrer"
        className="coffee-link"
      >
        ☕ Buy me a coffee
      </a>

      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} title="How It Works">
        <h3>Welcome to Poker Night!</h3>
        <p>
          Play <strong>No-Limit Texas Hold'em</strong> with friends right from your
          browser — no downloads or sign-ups required.
        </p>

        <h3>🎮 Getting Started</h3>
        <dl>
          <dt>Create Game</dt>
          <dd>
            Set up a new table with your preferred settings — blinds, starting chips,
            timers, rebuys, and more. You'll get a <strong>6-character room code</strong> to
            share with friends.
          </dd>
          <dt>Join Game</dt>
          <dd>
            Enter the room code and pick a display name and 4-digit PIN. Your PIN is
            your password — remember it so you can reconnect if you drop.
          </dd>
        </dl>

        <h3>🃏 Gameplay</h3>
        <ul>
          <li>Standard No-Limit Hold'em: preflop → flop → turn → river → showdown.</li>
          <li>Any player can deal the next hand once the current one finishes.</li>
          <li>Cards are hidden between hands — tap <strong>Show Cards</strong> to reveal yours.</li>
          <li>If enabled, blinds increase on a schedule and busted players can rebuy.</li>
        </ul>

        <h3>📱 Tips</h3>
        <ul>
          <li>Works on phones, tablets, and desktops — share via your local network.</li>
          <li>If you get disconnected, just rejoin with the same name and PIN.</li>
          <li>The game creator can pause the game at any time to freeze timers.</li>
        </ul>
      </HelpModal>
    </div>
  );
}
