import { request } from "./client.js";


export const fetchGhostPlaces = () =>
    request("/ghost-map/places");


export const fetchGhosts = () =>
    request("/ghost-map/ghosts");


export const fetchGhostStatus = () =>
    request("/ghost-map/status");


export const generateGhostMap = (payload) =>
    request("/ghost-map/generate", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });


export const fetchGhostMarks = () =>
    request("/ghost-map/marks");


export const createGhostMark = (mark) =>
    request("/ghost-map/marks", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(mark),
    });


export const deleteGhostMark = (markId) =>
    request(
        `/ghost-map/marks/${encodeURIComponent(markId)}`,
        { method: "DELETE" },
    );


export const fetchGhostRoads = (bbox) =>
    request(
        "/ghost-map/roads"
        + `?bbox=${encodeURIComponent(bbox)}`,
    );
