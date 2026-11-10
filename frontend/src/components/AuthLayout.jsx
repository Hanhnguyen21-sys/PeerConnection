import logo from "../assets/logo.jpg";
import studyGroup from "../assets/auth/study-group.jpg";
import noteTaking from "../assets/auth/note-taking.jpg";
import laptopCollab from "../assets/auth/laptop-collab.jpg";

export function BrandMark() {
  return (
    <div className="brand">
      <img src={logo} alt="" className="brand-logo" width="40" height="40" />
      <span className="brand-name">Peer Connections</span>
    </div>
  );
}

export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="auth">
      <aside className="auth-showcase">
        <BrandMark />
        <div className="showcase-copy">
          <p className="showcase-title">
            Learn together,
            <br />
            grow together
          </p>
          <p className="showcase-text">
            Peer Connections brings peer educators and SJSU's students into one
            shared space for tutoring and support.
          </p>
        </div>
        <div className="collage" aria-hidden="true">
          <img className="collage-main" src={studyGroup} alt="" />
          <img className="collage-tall" src={noteTaking} alt="" />
          <img className="collage-wide" src={laptopCollab} alt="" />
        </div>
      </aside>

      <main className="auth-panel">
        <div className="auth-card">
          <h1 className="auth-title">{title}</h1>
          <p className="auth-subtitle">{subtitle}</p>
          {children}
          {footer && <p className="auth-footer">{footer}</p>}
        </div>
      </main>
    </div>
  );
}
