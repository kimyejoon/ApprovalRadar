interface WindowWithWebkit extends Window {
  webkitAudioContext: typeof AudioContext;
}

export const playNotificationSound = () => {
  try {
    const AudioContext = window.AudioContext || (window as WindowWithWebkit).webkitAudioContext;
    if (!AudioContext) return;
    
    const audioCtx = new AudioContext();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    // Clean, modern notification sound
    oscillator.type = 'sine';
    
    // Play two quick notes
    const now = audioCtx.currentTime;
    
    // First note (higher)
    oscillator.frequency.setValueAtTime(880, now); // A5
    oscillator.frequency.exponentialRampToValueAtTime(440, now + 0.1);
    
    // Volume envelope
    gainNode.gain.setValueAtTime(0, now);
    gainNode.gain.linearRampToValueAtTime(0.3, now + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.3);

    oscillator.start(now);
    oscillator.stop(now + 0.3);
  } catch (e) {
    console.error("Audio playback failed", e);
  }
};
