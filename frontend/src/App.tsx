import { BrowserRouter, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import CreateGamePage from "./pages/CreateGamePage";
import JoinGamePage from "./pages/JoinGamePage";
import LobbyPage from "./pages/LobbyPage";
import TablePage from "./pages/TablePage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/create" element={<CreateGamePage />} />
        <Route path="/join" element={<JoinGamePage />} />
        <Route path="/game/:code" element={<LobbyPage />} />
        <Route path="/game/:code/table" element={<TablePage />} />
      </Routes>
    </BrowserRouter>
  );
}
