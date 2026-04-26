import { lazy, Suspense } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import { AnimatePresence } from "motion/react";
import { PageFrame } from "./components/layout/PageFrame";

const Overview   = lazy(() => import("./components/pages/Overview").then(m => ({ default: m.Overview })));
const Rankings   = lazy(() => import("./components/pages/Rankings").then(m => ({ default: m.Rankings })));
const Dimensions = lazy(() => import("./components/pages/Dimensions").then(m => ({ default: m.Dimensions })));
const Frontier   = lazy(() => import("./components/pages/Frontier").then(m => ({ default: m.Frontier })));
const Methods    = lazy(() => import("./components/pages/Methods").then(m => ({ default: m.Methods })));
const Blog       = lazy(() => import("./components/pages/Blog").then(m => ({ default: m.Blog })));

export default function App() {
  const location = useLocation();

  return (
    <PageFrame>
      <AnimatePresence mode="wait">
        {/* @ts-expect-error Routes definition lacks key but React needs it for AnimatePresence */}
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Suspense fallback={null}><Overview /></Suspense>} />
          <Route path="/rankings" element={<Suspense fallback={null}><Rankings /></Suspense>} />
          <Route path="/dimensions" element={<Suspense fallback={null}><Dimensions /></Suspense>} />
          <Route path="/frontier" element={<Suspense fallback={null}><Frontier /></Suspense>} />
          <Route path="/methods" element={<Suspense fallback={null}><Methods /></Suspense>} />
          <Route path="/blog" element={<Suspense fallback={null}><Blog /></Suspense>} />
        </Routes>
      </AnimatePresence>
    </PageFrame>
  );
}
