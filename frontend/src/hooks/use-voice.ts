"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, request } from "@/lib/api";

const MAX_RECORDING_MS = 60_000;

/**
 * Optional speech. Every failure path leaves text chat usable: unsupported browsers,
 * denied microphone permission, missing server models and playback errors all end in
 * a readable message and a released microphone.
 */
export function useVoice(onError: (message: string) => void) {
  const [enabled, setEnabled] = useState(false);
  const [listening, setListening] = useState(false);
  const [audioStatus, setAudioStatus] = useState("");
  const enabledRef = useRef(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const media = useRef<MediaStream | null>(null);
  const cancelled = useRef(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioUrl = useRef<string | null>(null);
  const audioRequest = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const report = useRef(onError);
  useEffect(() => {
    report.current = onError;
  });

  const stopAudio = useCallback(() => {
    setAudioStatus("");
    audioRequest.current?.abort();
    audioRequest.current = null;
    audio.current?.pause();
    if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
    audioUrl.current = null;
    audio.current = null;
  }, []);

  const cancelRecording = useCallback(() => {
    cancelled.current = true;
    if (recorder.current?.state === "recording") recorder.current.stop();
    media.current?.getTracks().forEach((t) => t.stop());
  }, []);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      cancelRecording();
      stopAudio();
    };
  }, [cancelRecording, stopAudio]);

  const toggleSpeech = useCallback(() => {
    enabledRef.current = !enabledRef.current;
    setEnabled(enabledRef.current);
    if (!enabledRef.current) stopAudio();
  }, [stopAudio]);

  const speak = useCallback(
    async (text: string) => {
      if (!enabledRef.current || !text) return;
      try {
        stopAudio();
        const controller = new AbortController();
        audioRequest.current = controller;
        setAudioStatus("Generando audio…");
        const response = await fetch("/api/voice/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({ text: text.slice(0, 3800) }),
        });
        if (!response.ok)
          throw new Error("No se pudo generar el audio. La respuesta escrita sigue disponible.");
        const blob = await response.blob();
        if (!enabledRef.current || controller.signal.aborted || !alive.current) return;
        const url = URL.createObjectURL(blob);
        audioUrl.current = url;
        const player = new Audio(url);
        audio.current = player;
        player.onended = stopAudio;
        player.onerror = () => {
          stopAudio();
          report.current("No se pudo reproducir el audio. La respuesta escrita sigue disponible.");
        };
        await player.play();
        setAudioStatus("Reproduciendo la respuesta…");
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        stopAudio();
        report.current(errorMessage(err));
      }
    },
    [stopAudio],
  );

  /** Start or stop dictation. Resolves the transcript through `onText`. */
  const listen = useCallback(
    async (onText: (text: string) => void) => {
      if (listening) {
        if (recorder.current?.state === "recording") recorder.current.stop();
        else {
          cancelled.current = true;
          setListening(false);
        }
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        report.current(
          "Grabación no disponible. Usa un navegador compatible en localhost o HTTPS; puedes seguir escribiendo.",
        );
        return;
      }
      cancelled.current = false;
      setListening(true);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (!alive.current || cancelled.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        media.current = stream;
        const rec = new MediaRecorder(stream);
        recorder.current = rec;
        const chunks: BlobPart[] = [];
        rec.ondataavailable = (e) => {
          if (e.data.size) chunks.push(e.data);
        };
        const timer = setTimeout(() => {
          if (rec.state === "recording") rec.stop();
        }, MAX_RECORDING_MS);
        rec.onerror = () => {
          clearTimeout(timer);
          stream.getTracks().forEach((t) => t.stop());
          setListening(false);
          report.current("No se pudo grabar el audio. Puedes seguir escribiendo.");
        };
        rec.onstop = async () => {
          clearTimeout(timer);
          stream.getTracks().forEach((t) => t.stop());
          if (!alive.current || cancelled.current) return;
          setListening(false);
          setAudioStatus("Transcribiendo…");
          try {
            const form = new FormData();
            form.append("file", new Blob(chunks, { type: rec.mimeType }), "recording.webm");
            const result = await request<{ text: string }>("/api/voice/transcribe", {
              method: "POST",
              body: form,
            });
            if (alive.current) onText(result.text);
          } catch (err) {
            if (alive.current) report.current(errorMessage(err));
          } finally {
            if (alive.current) setAudioStatus("");
          }
        };
        rec.start();
      } catch (err) {
        setListening(false);
        media.current?.getTracks().forEach((t) => t.stop());
        report.current(
          err instanceof Error && err.name === "NotAllowedError"
            ? "Permiso de micrófono denegado. Puedes seguir escribiendo."
            : errorMessage(err),
        );
      }
    },
    [listening],
  );

  return {
    speechEnabled: enabled,
    toggleSpeech,
    speak,
    stopAudio,
    audioStatus,
    listening,
    listen,
    cancelRecording,
  };
}
