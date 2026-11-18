import React, { useState, useEffect } from 'react';
import { Key, Eye, EyeOff, Check, Cpu } from 'lucide-react';

export default function KeyInput({ onKeySet, savedKey, localLlm }) {
    const [key, setKey] = useState(savedKey || '');
    const [isVisible, setIsVisible] = useState(false);
    const [isSaved, setIsSaved] = useState(!!savedKey);

    useEffect(() => {
        if (savedKey) setKey(savedKey);
    }, [savedKey]);

    const handleSave = () => {
        if (key.trim().length > 0) {
            onKeySet(key);
            setIsSaved(true);
        }
    };

    return (
        <div className="card p-4 sm:p-6 mb-8 animate-fade space-y-4">
            {localLlm && (
                <div className="p-3.5 bg-paper3 border border-rule rounded-input flex items-start gap-3">
                    <div className="p-1.5 bg-paper2 rounded-input text-ok shrink-0 mt-0.5">
                        <Cpu size={16} />
                    </div>
                    <div className="text-xs space-y-1">
                        <div className="font-medium text-ink flex items-center gap-2">
                            <span>Local AI Engine Active</span>
                            <span className="badge-ok text-[10px] py-0.5 px-2">100% Free & Local</span>
                        </div>
                        <p className="text-muted leading-relaxed">
                            Clip detection, transcript analysis, and visual moments are powered locally on this machine via <strong>Ollama ({localLlm.model || 'qwen3:1.7b'})</strong> and <strong>Moondream</strong>. No Gemini API key is needed to generate or download clips.
                        </p>
                    </div>
                </div>
            )}

            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-paper3 rounded-input text-brass">
                        <Key size={18} />
                    </div>
                    <h2 className="font-display lowercase text-lg text-ink">
                        {localLlm ? 'Gemini API Key (Optional Override)' : 'Gemini API Key'}
                    </h2>
                </div>
                {localLlm && <span className="badge-quiet text-xs">Optional</span>}
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative sm:flex-1">
                    <input
                        type={isVisible ? "text" : "password"}
                        value={key}
                        onChange={(e) => {
                            setKey(e.target.value);
                            setIsSaved(false);
                        }}
                        placeholder={localLlm ? "Leave blank to use local Ollama model..." : "AIzaSy..."}
                        className="input-field pr-12 font-mono"
                    />
                    <button
                        onClick={() => setIsVisible(!isVisible)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink transition-colors"
                    >
                        {isVisible ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                </div>
                <button
                    onClick={handleSave}
                    disabled={!key || isSaved}
                    className={isSaved ? 'badge-ok px-4 cursor-default' : 'btn-primary'}
                >
                    {isSaved ? <><Check size={14} /> Ready</> : 'Set Key'}
                </button>
            </div>
            <p className="mt-2 text-xs text-muted">
                {localLlm
                    ? 'Leave empty to use 100% local processing. If provided, OpenShorts can route cloud tasks through Google Cloud AI Studio.'
                    : 'Your key is stored locally in your browser for convenience.'}
                <br />
                <a
                    href="https://aistudio.google.com/app/apikey"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brass hover:underline mt-1 inline-block"
                >
                    Get a Gemini API Key here (if you wish to use Google Cloud) →
                </a>
            </p>
        </div>
    );
}
