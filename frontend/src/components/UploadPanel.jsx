import { useId, useRef, useState } from 'react';

// File picker with drag and drop. The page owns what happens to the file.
export default function UploadPanel({ accept, hint, disabled, progress, busyLabel, onFile }) {
  const inputId = useId();
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const choose = (file) => {
    if (file && !disabled) onFile(file);
  };

  return (
    <div
      className={`dropzone${dragging ? ' is-dragging' : ''}${disabled ? ' is-disabled' : ''}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        choose(event.dataTransfer.files[0]);
      }}
    >
      {disabled ? (
        <div className="progress-block" role="status">
          <span>{progress < 100 ? `Uploading ${progress}%` : busyLabel}</span>
          <div className="progress-track">
            <div className={`progress-fill${progress >= 100 ? ' is-working' : ''}`} style={{ width: `${progress}%` }} />
          </div>
        </div>
      ) : (
        <>
          <span className="dropzone-icon">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V5M7.5 9.5L12 5l4.5 4.5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />
            </svg>
          </span>
          <label htmlFor={inputId} className="button button-primary">
            Choose a file
          </label>
          <span className="dropzone-hint">{hint}</span>
        </>
      )}
      <input
        id={inputId}
        ref={inputRef}
        className="visually-hidden"
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(event) => {
          choose(event.target.files[0]);
          // Lets the same file be chosen again after an error.
          inputRef.current.value = '';
        }}
      />
    </div>
  );
}
