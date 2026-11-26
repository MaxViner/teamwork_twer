import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import UploadPanel from "../components/ui/uploadPanel/UploadPanel.jsx";
import JobsPanel from "../components/panels/jobsPanel/JobsPanel.jsx";
import FooterNav from "../layout/FooterNav.jsx";
import PageHeader from "../layout/PageHeader.jsx";
import JobStatusSection from "./JobStatusSection.jsx";
import InspectionShell from "./InspectionShell.jsx";
import { ANALYSIS_SECTIONS } from "../constants/sectionsNav.js";
import { useVideoAnalysisController } from "../hooks/useVideoAnalysisController.js";

export default function VideoAnalysisApp() {
    const state = useVideoAnalysisController();

    return (
        <main className="app">
            <PageHeader />

            <ErrorBanner
                message={state.error}
                onClose={state.clearError}
            />

            <UploadPanel
                key={state.uploadPanelKey}
                uploading={state.uploading}
                uploadProgress={state.uploadProgress}
                preparing={state.preparing}
                prepareProgress={state.prepareProgress}
                prepareMessage={state.prepareMessage}
                onUpload={state.actions.handleUpload}
            />

            <JobsPanel
                jobs={state.jobs}
                selectedId={state.selectedId}
                job={state.job}
                onSelect={state.setSelectedId}
                onRefresh={state.actions.handleRefreshJobs}
                onDelete={state.actions.handleDeleteJob}
                onPause={state.actions.handlePauseJob}
                onResume={state.actions.handleResumeJob}
            />

            {state.job && (
                <>
                    <JobStatusSection
                        job={state.job}
                        busy={state.busy}
                        onRetry={state.actions.handleRetry}
                        onRemove={state.actions.handleRemove}
                    />

                    <InspectionShell
                        job={state.job}
                        observations={state.observations}
                        video={state.video}
                        onError={state.onError}
                        onRetry={state.actions.handleRetry}
                    />

                    <FooterNav sections={ANALYSIS_SECTIONS} />
                </>
            )}
        </main>
    );
}
