import { Outlet, ScrollRestoration } from "react-router-dom";
import "./App.css";

export default function App() {
  return (
    <>
      <ScrollRestoration />
      <Outlet />
    </>
  );
}
