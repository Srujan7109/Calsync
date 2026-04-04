import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Calendar, Menu, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const Navbar: React.FC = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handler);
    return () => window.removeEventListener('scroll', handler);
  }, []);

  const isLanding = location.pathname === '/';

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
      scrolled ? 'glass border-b border-border py-3' : 'bg-transparent py-5'
    }`}>
      <div className="max-w-7xl mx-auto px-6 flex items-center justify-between">
        {/* Logo */}
        <button onClick={() => navigate('/')} className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center group-hover:bg-accent-glow transition-colors duration-300">
            <Calendar className="w-4 h-4 text-white" />
          </div>
          <span className="font-display font-bold text-xl text-white tracking-tight">
            CalSync<span className="text-accent-glow">.ai</span>
          </span>
        </button>

        {/* Desktop Nav */}
        {isLanding && (
          <div className="hidden md:flex items-center gap-8">
            {['Features', 'How it works', 'Pricing'].map(item => (
              <a
                key={item}
                href={`#${item.toLowerCase().replace(/ /g, '-')}`}
                className="text-muted hover:text-soft text-sm font-body transition-colors duration-200"
              >
                {item}
              </a>
            ))}
          </div>
        )}

        {/* CTA */}
        <div className="hidden md:flex items-center gap-3">
          {user ? (
            <>
              <button
                onClick={() => navigate('/dashboard')}
                className="text-sm text-muted hover:text-soft transition-colors font-body"
              >
                Dashboard
              </button>
              <button
                onClick={signOut}
                className="text-sm text-muted hover:text-soft transition-colors font-body"
              >
                Sign out
              </button>
              <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-xs font-semibold">
                {user.avatar}
              </div>
            </>
          ) : (
            <>
              <button
                onClick={() => navigate('/signin')}
                className="text-sm text-muted hover:text-soft transition-colors font-body px-4 py-2"
              >
                Sign in
              </button>
              <button
                onClick={() => navigate('/signup')}
                className="btn-primary text-sm px-5 py-2.5"
              >
                Get started free
              </button>
            </>
          )}
        </div>

        {/* Mobile */}
        <button
          className="md:hidden text-muted hover:text-soft"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div className="md:hidden glass border-t border-border mt-2 py-4 px-6 space-y-3">
          {isLanding && ['Features', 'How it works', 'Pricing'].map(item => (
            <a
              key={item}
              href={`#${item.toLowerCase().replace(/ /g, '-')}`}
              className="block text-muted hover:text-soft text-sm font-body py-1"
              onClick={() => setMobileOpen(false)}
            >
              {item}
            </a>
          ))}
          {user ? (
            <>
              <button onClick={() => { navigate('/dashboard'); setMobileOpen(false); }} className="block w-full text-left text-sm text-soft py-1">Dashboard</button>
              <button onClick={() => { signOut(); setMobileOpen(false); }} className="block w-full text-left text-sm text-muted py-1">Sign out</button>
            </>
          ) : (
            <>
              <button onClick={() => { navigate('/signin'); setMobileOpen(false); }} className="block w-full text-left text-sm text-muted py-1">Sign in</button>
              <button onClick={() => { navigate('/signup'); setMobileOpen(false); }} className="btn-primary text-sm w-full text-center">Get started</button>
            </>
          )}
        </div>
      )}
    </nav>
  );
};

export default Navbar;
