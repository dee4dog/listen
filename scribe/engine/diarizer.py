"""Speaker separation: ECAPA voice embeddings per transcript segment, clustered
into speakers, labelled 'Speaker 1..N' in order of first appearance.

Degrades gracefully: if the embedding stack is unavailable, everything is
assigned to a single speaker instead of failing the whole pipeline.
"""
import numpy as np

MIN_EMBED_SECONDS = 0.6
SR = 16000


def _load_encoder(models_dir):
    try:
        from speechbrain.inference.speaker import EncoderClassifier
    except ImportError:  # older speechbrain
        from speechbrain.pretrained import EncoderClassifier
    kwargs = {}
    try:
        # Symlinking (the default) needs admin rights on Windows; download
        # the model files directly into savedir instead.
        from speechbrain.utils.fetching import LocalStrategy
        kwargs["local_strategy"] = LocalStrategy.COPY_SKIP_CACHE
    except ImportError:
        pass
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(models_dir / "ecapa"),
        **kwargs,
    )


def diarize(audio_path, segments, models_dir, sensitivity=0.55, progress=None):
    """Assign speaker labels in place. Returns (segments, centroids {label: ndarray})."""
    if not segments:
        return segments, {}

    try:
        import torch
        from faster_whisper.audio import decode_audio
        encoder = _load_encoder(models_dir)
    except Exception as exc:
        if progress:
            progress(f"Speaker separation unavailable ({exc}); using a single speaker.")
        for seg in segments:
            seg.speaker = "Speaker 1"
        return segments, {}

    if progress:
        progress("Analyzing voices…")
    wav = decode_audio(str(audio_path), sampling_rate=SR)

    embeddable, embs = [], []
    for i, seg in enumerate(segments):
        chunk = wav[int(seg.start * SR):int(seg.end * SR)]
        if len(chunk) < MIN_EMBED_SECONDS * SR:
            continue
        with torch.no_grad():
            emb = encoder.encode_batch(
                torch.from_numpy(np.ascontiguousarray(chunk)).float().unsqueeze(0)
            ).squeeze().cpu().numpy()
        emb = emb / (np.linalg.norm(emb) + 1e-9)
        embeddable.append(i)
        embs.append(emb)
        if progress and len(embs) % 25 == 0:
            progress(f"Analyzing voices… {len(embs)} segments")

    if not embs:
        for seg in segments:
            seg.speaker = "Speaker 1"
        return segments, {}

    X = np.stack(embs)
    if len(embs) == 1:
        labels = np.zeros(1, dtype=int)
    else:
        from sklearn.cluster import AgglomerativeClustering
        labels = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=float(sensitivity),
            metric="cosine",
            linkage="average",
        ).fit_predict(X)

    # Number speakers by order of first appearance.
    order = []
    for lab in labels:
        if lab not in order:
            order.append(lab)
    names = {lab: f"Speaker {rank}" for rank, lab in enumerate(order, start=1)}
    for idx, lab in zip(embeddable, labels):
        segments[idx].speaker = names[lab]

    # Short segments that couldn't be embedded inherit a neighbour's speaker.
    last = None
    for seg in segments:
        if seg.speaker:
            last = seg.speaker
        elif last:
            seg.speaker = last
    nxt = None
    for seg in reversed(segments):
        if seg.speaker:
            nxt = seg.speaker
        else:
            seg.speaker = nxt or "Speaker 1"

    centroids = {}
    for lab in order:
        c = X[labels == lab].mean(axis=0)
        centroids[names[lab]] = c / (np.linalg.norm(c) + 1e-9)
    return segments, centroids


def match_known_speakers(centroids, known, threshold=0.70):
    """Match cluster centroids against saved voice profiles.

    `known` is [(name, embedding)]. Returns {generic_label: known_name} for
    matches above `threshold` cosine similarity; each known name used once.
    """
    mapping, used = {}, set()
    for label, centroid in centroids.items():
        best_name, best_sim = None, float(threshold)
        for name, emb in known:
            if name in used or emb.shape != centroid.shape:
                continue
            sim = float(np.dot(centroid, emb))
            if sim > best_sim:
                best_name, best_sim = name, sim
        if best_name:
            mapping[label] = best_name
            used.add(best_name)
    return mapping
