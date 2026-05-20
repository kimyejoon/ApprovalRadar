const envApiUrl = import.meta.env.VITE_API_URL;
export const API_BASE_URL = envApiUrl !== undefined 
  ? (envApiUrl === '' ? window.location.origin : envApiUrl) 
  : 'http://localhost:8000';
