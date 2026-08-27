function updateQuantifiedSelfData() {
  const targetSpreadsheetId = 'YOUR_SPREADSHEET_ID'; // Replace with actual ID
  const sheetName = 'Quantified Self';
  
  // 1. Define the Regex Map for Nomenclature Variations
  const medicalRegexMap = {
    'ApoB': /apob|apolipoprotein\s*b/i,
    'LDL cholesterol': /ldl|ldl-c|ldl\s*cholesterol/i,
    'HDL cholesterol': /hdl|hdl-c|hdl\s*cholesterol/i,
    'Triglycerides': /triglycerides|trigs|tg/i,
    'HbA1c': /hba1c|a1c|glycated\s*hemoglobin/i,
    'Ferritin': /ferritin/i,
    'Vitamin D': /vitamin\s*d|vit\s*d|25\(oh\)d/i,
    'hs-CRP': /hs-crp|hscrp|crp|c-reactive\s*protein/i,
    'ALT': /alt|alanine\s*aminotransferase|sgpt/i,
    'GGT': /ggt|gamma-gt|gamma-glutamyl\s*transferase/i,
    'Creatinine/eGFR': /creatinine|egfr|gfr/i,
    'TSH': /tsh|thyroid\s*stimulating\s*hormone/i,
    'Lp(a) (nmol/l)': /lp\(a\)|lipoprotein\s*a/i 
  };

  const dailyRecords = {};

  // 2. Process Garmin Data
  const garminFiles = DriveApp.getFilesByName("drw_garmin_data.csv");
  if (garminFiles.hasNext()) {
    const garminData = Utilities.parseCsv(garminFiles.next().getBlob().getDataAsString());
    const garminHeaders = garminData[0];
    const dateIndex = garminHeaders.findIndex(h => /date/i.test(h));
    
    // Start from row 1 to skip headers
    for (let i = 1; i < garminData.length; i++) {
      const row = garminData[i];
      if (!row[dateIndex]) continue;
      
      const dateKey = new Date(row[dateIndex]).toISOString().split('T')[0];
      
      dailyRecords[dateKey] = {
        'Date': dateKey,
        'DOB': '1985-10-25', // Static replacement for Age
        'Physiological Max HR': row[4], // Extracted directly from Column E (index 4)
        'Garmin_Raw': row 
      };
    }
  }

  // 3. Process Medical Data
  const medicalFiles = DriveApp.getFilesByName("Daniel's Medical Test Results.csv");
  if (medicalFiles.hasNext()) {
    const medData = Utilities.parseCsv(medicalFiles.next().getBlob().getDataAsString());
    const medHeaders = medData[0];
    const medDateIndex = medHeaders.findIndex(h => /date/i.test(h));
    
    // Map column indices to the required biomarkers
    const colMapping = {};
    for (let i = 0; i < medHeaders.length; i++) {
      for (const [key, regex] of Object.entries(medicalRegexMap)) {
        if (regex.test(medHeaders[i])) {
          colMapping[key] = i;
        }
      }
    }

    for (let i = 1; i < medData.length; i++) {
      const row = medData[i];
      if (!row[medDateIndex]) continue;
      
      const dateKey = new Date(row[medDateIndex]).toISOString().split('T')[0];
      
      if (!dailyRecords[dateKey]) {
        dailyRecords[dateKey] = { 'Date': dateKey, 'DOB': '1985-10-25' };
      }
      
      // Populate extracted medical values
      for (const [biomarker, colIndex] of Object.entries(colMapping)) {
        dailyRecords[dateKey][biomarker] = row[colIndex];
      }
    }
  }

  // 4. Construct Final Array and Sort
  const outputHeaders = [
    'Date', 'DOB', 'Physiological Max HR', 'Lp(a) (nmol/l)',
    'ApoB', 'LDL cholesterol', 'HDL cholesterol', 'Triglycerides',
    'HbA1c', 'Ferritin', 'Vitamin D', 'hs-CRP', 'ALT', 'GGT', 'Creatinine/eGFR', 'TSH'
  ];

  const finalArray = [];
  
  // Convert dictionary to array
  for (const date in dailyRecords) {
    const record = dailyRecords[date];
    const rowArray = outputHeaders.map(header => record[header] || "");
    finalArray.push(rowArray);
  }

  // Sort descending (most recent first)
  finalArray.sort((a, b) => new Date(b[0]) - new Date(a[0]));
  
  // Prepend headers
  finalArray.unshift(outputHeaders);

  // 5. Write to Sheet
  const sheet = SpreadsheetApp.openById(targetSpreadsheetId).getSheetByName(sheetName);
  sheet.clearContents();
  sheet.getRange(1, 1, finalArray.length, finalArray[0].length).setValues(finalArray);
}
