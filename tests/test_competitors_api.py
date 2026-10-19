def test_create_competitor_queues_sync_job(client):
    response = client.post("/competitors", json={"username": "@growthhacker"})
    assert response.status_code == 201
    data = response.json()
    assert data["competitor"]["username"] == "growthhacker"
    assert data["competitor"]["status"] == "active"
    assert data["job"]["job_type"] == "initial_profile_sync"
    assert data["job"]["status"] == "queued"


def test_list_and_get_competitor(client):
    client.post("/competitors", json={"username": "fitnesspro"})
    list_res = client.get("/competitors")
    assert list_res.status_code == 200
    competitors = list_res.json()
    assert any(c["username"] == "fitnesspro" for c in competitors)

    comp_id = next(c["id"] for c in competitors if c["username"] == "fitnesspro")
    get_res = client.get(f"/competitors/{comp_id}")
    assert get_res.status_code == 200
    assert get_res.json()["username"] == "fitnesspro"


def test_update_and_delete_competitor(client):
    res = client.post("/competitors", json={"username": "to_delete"})
    comp_id = res.json()["competitor"]["id"]

    patch_res = client.patch(f"/competitors/{comp_id}", json={"status": "paused"})
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "paused"

    del_res = client.delete(f"/competitors/{comp_id}")
    assert del_res.status_code == 200

    get_again = client.get(f"/competitors/{comp_id}")
    assert get_again.status_code == 404


def test_trigger_sync_job(client):
    res = client.post("/competitors", json={"username": "sync_target"})
    comp_id = res.json()["competitor"]["id"]

    sync_res = client.post(f"/competitors/{comp_id}/sync")
    assert sync_res.status_code == 202
    assert sync_res.json()["job_type"] == "incremental_profile_sync"
    assert sync_res.json()["status"] == "queued"
