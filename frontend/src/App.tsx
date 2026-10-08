import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";

// Each page is its own chunk, so the charts library only loads once a page that draws charts is opened.
const Overview = lazy(() => import("./pages/Overview"));
const Journey = lazy(() => import("./pages/Journey"));
const Assistant = lazy(() => import("./pages/Assistant"));
const Risk = lazy(() => import("./pages/Risk"));
const Matching = lazy(() => import("./pages/Matching"));
const Briefs = lazy(() => import("./pages/Briefs"));
const Strategy = lazy(() => import("./pages/Strategy"));
const Roll = lazy(() => import("./pages/Roll"));
const DataPage = lazy(() => import("./pages/Data"));

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="journey" element={<Journey />} />
          <Route path="ai" element={<Assistant />} />
          <Route path="risk" element={<Risk />} />
          <Route path="matching" element={<Matching />} />
          <Route path="briefs" element={<Briefs />} />
          <Route path="strategy" element={<Strategy />} />
          <Route path="roll" element={<Roll />} />
          <Route path="data" element={<DataPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
