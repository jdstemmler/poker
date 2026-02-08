import { Link } from "react-router-dom";

export default function HomePage() {
  return (
    <div className="page home-page">
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
        href="https://buymeacoffee.com/jdstemmler"
        target="_blank"
        rel="noopener noreferrer"
        className="coffee-link"
      >
        ☕ Buy me a coffee
      </a>
    </div>
  );
}
