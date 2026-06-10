const setValue = (id, value) => {
  const field = document.getElementById(id);
  if (field) field.value = value || "";
};

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const message = form.getAttribute("data-confirm") || "진행할까요?";
    if (!window.confirm(message)) {
      event.preventDefault();
    }
  });
});

document.querySelectorAll("[data-edit-speech]").forEach((button) => {
  button.addEventListener("click", () => {
    const data = button.dataset;
    const form = document.getElementById("speechEditForm");
    form.action = `/speeches/${data.id}/update`;
    setValue("speech_edit_date", data.speechDate);
    setValue("speech_edit_actor", data.actor);
    setValue("speech_edit_organization", data.organization);
    setValue("speech_edit_venue", data.venue);
    setValue("speech_edit_quote", data.quote);
    setValue("speech_edit_keywords", data.keywords);
    setValue("speech_edit_source_title", data.sourceTitle);
    setValue("speech_edit_source_url", data.sourceUrl);
    setValue("speech_edit_source_name", data.sourceName);
  });
});

document.querySelectorAll("[data-edit-incident]").forEach((button) => {
  button.addEventListener("click", () => {
    const data = button.dataset;
    const form = document.getElementById("incidentEditForm");
    form.action = `/incidents/${data.id}/update`;
    setValue("incident_edit_date", data.accidentDate);
    setValue("incident_edit_company", data.companyName);
    setValue("incident_edit_summary", data.accidentSummary);
    setValue("incident_edit_response", data.externalResponse);
    setValue("incident_edit_implication", data.implication);
    setValue("incident_edit_apology", data.apologyText);
    setValue("incident_edit_source_title", data.sourceTitle);
    setValue("incident_edit_source_url", data.sourceUrl);
    setValue("incident_edit_source_name", data.sourceName);
  });
});

document.querySelectorAll("[data-edit-company-accident]").forEach((button) => {
  button.addEventListener("click", () => {
    const data = button.dataset;
    const form = document.getElementById("companyAccidentEditForm");
    form.action = `/company-accidents/${data.id}/update`;
    setValue("company_edit_description", data.incidentDescription);
    setValue("company_edit_apology", data.apologyText);
    setValue("company_edit_response", data.responseDirection);
  });
});

const activateTabFromHash = () => {
  const hash = window.location.hash;
  if (!hash) return;
  const trigger = document.querySelector(`[data-bs-target="${hash}"]`);
  if (trigger && window.bootstrap) {
    window.bootstrap.Tab.getOrCreateInstance(trigger).show();
  }
};

document.querySelectorAll('[data-bs-toggle="tab"]').forEach((trigger) => {
  trigger.addEventListener("shown.bs.tab", (event) => {
    const target = event.target.getAttribute("data-bs-target");
    if (target) history.replaceState(null, "", target);
  });
});

activateTabFromHash();
