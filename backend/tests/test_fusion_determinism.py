import pytest
from app.transcription.hybrid_fusion import (
    fuse_rover,
    fuse_conservative_agreement,
    align_hypotheses_pairwise,
    tokenize_transcript,
)

def test_rover_determinism():
    h1 = {"model_id": "codeswitched-medium", "text": "هو راح ال conference امبارح وقال كلام مهم جدا في ال meeting"}
    h2 = {"model_id": "large-v3-turbo", "text": "هو راح المؤتمر امبارح وقال كلام مهم جدا في الاجتماع"}
    h3 = {"model_id": "qwencleo-asr-4bit", "text": "هو راح ال conference امبارح وقال كلام مهم في ال meeting"}
    
    res1 = fuse_rover([h1, h2, h3])
    res2 = fuse_rover([h1, h2, h3])
    res3 = fuse_rover([h1, h2, h3])
    
    assert res1["fused_text"] == res2["fused_text"]
    assert res2["fused_text"] == res3["fused_text"]
    assert len(res1["fused_text"].split()) > 5

def test_conservative_determinism():
    t1 = "المسرح بتاعها ان هو يهوست ال event نفسه"
    t2 = "المسرح بتاعها ان هو يعني نفسه"
    res1 = fuse_conservative_agreement(t1, t2)
    res2 = fuse_conservative_agreement(t1, t2)
    assert res1["fused_text"] == res2["fused_text"]
