import { Link } from "react-router-dom";

export default function HomePage() {
  return (
    <div className="page">
      <h1>♠ Poker Night</h1>
      <p>No-Limit Texas Hold'em</p>
      <div className="button-group">
        <Link to="/create" className="btn btn-primary">
          Create Game
        </Link>
        <Link to="/join" className="btn btn-secondary">
          Join Game
        </Link>
      </div>
    </div>
  );
}
