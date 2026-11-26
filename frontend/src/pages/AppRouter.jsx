import { BrowserRouter, Routes, Route } from "react-router-dom";

import VideoAnalysisApp from "../sections/VideoAnalysisApp.jsx";
import DevLayout from "./dev/DevLayout.jsx";
import DevHomePage from "./dev/DevHomePage.jsx";
import VisionTestPage from "./dev/VisionTestPage.jsx";
import AiChatTestPage from "./dev/AiChatTestPage.jsx";
import VideoLabPage from "./dev/VideoLabPage.jsx";
import OdometryLabPage from "./dev/OdometryLabPage.jsx";
import GeoResearchPage from "./dev/GeoResearchPage.jsx";
import NotFoundPage from "./NotFoundPage.jsx";

export default function AppRoutes() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<VideoAnalysisApp />} />


                <Route path="/dev" element={<DevLayout />}>
                    <Route index element={<DevHomePage />} />
                    <Route path="vision" element={<VisionTestPage />} />
                    <Route path="chat" element={<AiChatTestPage />} />
                    <Route path="video-lab" element={<VideoLabPage />} />
                    <Route path="odometry" element={<OdometryLabPage />} />
                    <Route path="map" element={<GeoResearchPage />} />
                </Route>


                <Route path="*" element={<NotFoundPage />} />
            </Routes>
        </BrowserRouter>
    );
}
