import { BrowserRouter, Routes, Route } from "react-router-dom";

import VideoAnalysisApp from "../sections/VideoAnalysisApp.jsx";
import DevLayout from "./DevLayout.jsx";
import DevHomePage from "./DevHomePage.jsx";
import VisionTestPage from "./VisionTestPage.jsx";
import AiChatTestPage from "./AiChatTestPage.jsx";
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
                </Route>


                <Route path="*" element={<NotFoundPage />} />
            </Routes>
        </BrowserRouter>
    );
}